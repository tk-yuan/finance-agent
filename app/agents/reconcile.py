"""月末批量对账：用 LangGraph 编排多节点流程。

流程：拆分 → 核对 → 汇总
- 拆分：把整月账目按科目分组（拆成多个核对批次）
- 核对：对每批跑异常检测规则（确定性，代码实现）
- 汇总：合并所有异常，生成对账报告

为什么异常检测用规则而不是 LLM：
异常判断是确定性的（大额、重复、信息缺失），规则 100% 可靠且快；
LLM 反而会漏判、误判。这是「确定性交给代码，理解交给模型」的又一体现。
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

# 异常检测规则阈值
# 注意：企业单笔几万很正常，阈值要按规模设定，否则全是误报
LARGE_AMOUNT = 150000.0  # 单笔超过此金额视为大额异常


class ReconcileState(TypedDict):
    entries: list  # 待核对的账目 [{date, amount, description, category, entry_type}]
    batches: dict  # 按科目分组后的批次 {category: [entries]}
    anomalies: list  # 发现的异常
    report: str  # 最终对账报告


def split_entries(state: ReconcileState) -> dict:
    """节点1：按科目把账目拆成多个批次。"""
    batches: dict[str, list] = {}
    for e in state["entries"]:
        batches.setdefault(e["category"], []).append(e)
    return {"batches": batches}


def check_batches(state: ReconcileState) -> dict:
    """节点2：对每批跑异常检测规则。"""
    anomalies: list[str] = []
    seen: dict[tuple, int] = {}
    for category, entries in state["batches"].items():
        for e in entries:
            is_expense = e.get("entry_type") == "expense"

            # 规则1：大额支出（只查支出，收入不属于"支出异常"）
            if is_expense and e["amount"] > LARGE_AMOUNT:
                anomalies.append(
                    f"⚠️ 大额支出：{e['date']} {e['description']} {e['amount']:.2f}元（{category}）"
                )

            # 规则2：疑似重复记账（同日+同描述+同金额）
            key = (e["date"], e["description"], e["amount"])
            seen[key] = seen.get(key, 0) + 1
            if seen[key] == 2:
                anomalies.append(
                    f"🔁 疑似重复：{e['date']} {e['description']} {e['amount']:.2f}元 出现多次"
                )

            # 规则3：描述信息不全
            if len((e.get("description") or "").strip()) < 2:
                anomalies.append(f"❓ 描述过短：{e['date']} {e['amount']:.2f}元（{category}）")
    return {"anomalies": anomalies}


def summarize(state: ReconcileState) -> dict:
    """节点3：汇总异常，生成报告。"""
    n = len(state["entries"])
    anomalies = state["anomalies"]
    if not anomalies:
        report = f"✅ 本月 {n} 笔账目核对完成，未发现异常。"
    else:
        report = f"本月 {n} 笔账目，发现 {len(anomalies)} 处异常：\n" + "\n".join(anomalies)
    return {"report": report}


def build_reconcile_graph():
    """构建对账状态图。"""
    graph = StateGraph(ReconcileState)
    graph.add_node("split", split_entries)
    graph.add_node("check", check_batches)
    graph.add_node("summarize", summarize)
    graph.add_edge(START, "split")
    graph.add_edge("split", "check")
    graph.add_edge("check", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


_reconcile = build_reconcile_graph()


def reconcile_entries(entries: list[dict]) -> str:
    """对账入口：输入账目列表，返回对账报告。"""
    result = _reconcile.invoke({"entries": entries, "batches": {}, "anomalies": [], "report": ""})
    return result["report"]
