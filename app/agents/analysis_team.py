"""财务分析多智能体团队。

为什么这里用多智能体（而不是像查询那样用单 Agent）：

    ① 视角不同 —— 盈利能力看利润表、偿债能力看资产负债表、
       营运能力看往来周转、风险排查看异常。每个角色需要不同的
       分析框架和输出结构，塞进一个 Agent 会互相干扰。
    ② 可以并行 —— 四个分析互不依赖，并行跑比串行快得多。
    ③ 上下文可控 —— 一年几百笔账全塞给一个 Agent 会撑爆上下文，
       拆开后每个角色只看自己需要的数据。

但它也**不该滥用**：记账、审核、结账这些确定性任务，
用规则比用多智能体快、准、省钱——所以那些地方一个 Agent 都没有。

数据流：
    ┌─ 盈利能力分析 ─┐
    ├─ 偿债能力分析 ─┤
    ├─ 营运能力分析 ─┼─→ 汇总成分析报告
    └─ 风险排查 ────┘
"""

from __future__ import annotations

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.core.llm import get_chat_model
from app.services import finance_analysis


class AnalysisState(TypedDict):
    metrics: dict          # 四个维度的指标（代码算好的）
    profitability: str     # 盈利能力分析
    solvency: str          # 偿债能力分析
    efficiency: str        # 营运能力分析
    risk: str              # 风险排查
    report: str            # 汇总报告


def _ask(role: str, duty: str, data: dict, focus: str) -> str:
    """让一个"专家角色"解读数据。

    关键：指标是代码算好的，模型只负责解读。
    提示词里明确要求"不要自己算数，用我给的数据"。
    """
    import json

    system = (
        f"你是财务分析专家，专门负责「{role}」。\n"
        f"{duty}\n\n"
        "【重要】下面的数据已经由系统精确计算好了，"
        "**你只负责解读这些数字的含义，不要自己重新计算或改动任何数据**。\n"
        "分析要具体：指出数字说明什么问题、和常见水平比怎么样、"
        "有什么值得关注或警惕的地方。\n"
        "用简洁的中文，150 字以内，不要用 markdown 标题。"
    )
    user = f"请分析以下数据：\n{json.dumps(data, ensure_ascii=False, indent=2)}\n\n{focus}"

    resp = get_chat_model().invoke([
        SystemMessage(content=system),
        HumanMessage(content=user),
    ])
    return str(getattr(resp, "content", "")).strip()


# ---------- 四个分析节点（互相独立，可并行）----------

def analyze_profitability(state: AnalysisState) -> dict:
    """盈利能力：这家公司赚钱吗、赚得高效吗。"""
    data = state["metrics"]["profitability"]
    return {"profitability": _ask(
        role="盈利能力分析",
        duty="关注毛利率、净利率、费用率，判断盈利水平和成本控制能力。",
        data=data,
        focus="重点说明：毛利和净利的差距说明费用控制得怎么样？"
              "这个盈利水平对小微企业来说正常吗？",
    )}


def analyze_solvency(state: AnalysisState) -> dict:
    """偿债能力：欠的钱还得起吗、资金链安全吗。"""
    data = state["metrics"]["solvency"]
    return {"solvency": _ask(
        role="偿债能力分析",
        duty="关注资产负债率、流动比率，判断短期偿债压力和资金安全。",
        data=data,
        focus="重点说明：资产负债率是否偏高？流动资金够不够周转？"
              "有没有资金链紧张的风险？",
    )}


def analyze_efficiency(state: AnalysisState) -> dict:
    """营运能力：资产周转快不快、赊销风险大不大。"""
    data = state["metrics"]["efficiency"]
    return {"efficiency": _ask(
        role="营运能力分析",
        duty="关注应收账款/应付账款周转率、赊销占比，判断资金占用和回款效率。",
        data=data,
        focus="重点说明：赊销占比高不高？应收账款周转是否健康？"
              "会不会有回款不畅的问题？",
    )}


def analyze_risk(state: AnalysisState) -> dict:
    """风险排查：有没有雷。"""
    data = state["metrics"]["risk"]
    return {"risk": _ask(
        role="财务风险排查",
        duty="关注大额异常支出、摘要缺失、客户集中度等风险信号。",
        data=data,
        focus="重点说明：最值得警惕的风险点是什么？"
              "客户集中度高不高？需要采取什么措施？",
    )}


# ---------- 汇总节点 ----------

def summarize(state: AnalysisState) -> dict:
    """把四份分析汇总成一份体检报告。"""
    parts = {
        "盈利能力": state.get("profitability", ""),
        "偿债能力": state.get("solvency", ""),
        "营运能力": state.get("efficiency", ""),
        "风险排查": state.get("risk", ""),
    }
    key_metrics = {
        "营业收入": state["metrics"]["profitability"]["营业收入"],
        "净利润": state["metrics"]["profitability"]["净利润"],
        "毛利率": state["metrics"]["profitability"]["毛利率"],
        "净利率": state["metrics"]["profitability"]["净利率"],
        "资产负债率": state["metrics"]["solvency"]["资产负债率"],
        "流动资金": state["metrics"]["solvency"]["流动资金"],
        "客户集中度": state["metrics"]["risk"]["客户集中度"],
    }

    import json

    system = (
        "你是财务总监，负责把四位分析师的报告汇总成一份给老板看的"
        "「财务体检报告」。\n"
        "要求：\n"
        "1. 开头一句话给出整体结论（健康 / 尚可 / 需警惕）\n"
        "2. 分「亮点」和「风险」两块，各 2-3 条\n"
        "3. 最后给 2-3 条具体可执行的建议\n"
        "4. 不要重复罗列原始数字，要说数字背后的意思\n"
        "5. 简洁，中文，300 字以内"
    )
    user = (
        f"关键指标：\n{json.dumps(key_metrics, ensure_ascii=False, indent=2)}\n\n"
        f"四位分析师的意见：\n{json.dumps(parts, ensure_ascii=False, indent=2)}"
    )

    resp = get_chat_model().invoke([
        SystemMessage(content=system),
        HumanMessage(content=user),
    ])
    return {"report": str(getattr(resp, "content", "")).strip()}


def build_analysis_graph():
    """编排：四个分析并行，然后汇总。

    LangGraph 里从 START 同时连到多个节点就会并行执行，
    它们都连到 summarize 时，summarize 会等全部完成再跑。
    """
    graph = StateGraph(AnalysisState)

    graph.add_node("profitability", analyze_profitability)
    graph.add_node("solvency", analyze_solvency)
    graph.add_node("efficiency", analyze_efficiency)
    graph.add_node("risk", analyze_risk)
    graph.add_node("summarize", summarize)

    # 四个分析并行启动
    graph.add_edge(START, "profitability")
    graph.add_edge(START, "solvency")
    graph.add_edge(START, "efficiency")
    graph.add_edge(START, "risk")

    # 全部汇到汇总节点
    for node in ("profitability", "solvency", "efficiency", "risk"):
        graph.add_edge(node, "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()


_graph = build_analysis_graph()


def run_analysis() -> dict:
    """跑一次完整的财务分析，返回四份专项分析 + 汇总报告。"""
    metrics = finance_analysis.all_metrics()
    result = _graph.invoke({
        "metrics": metrics,
        "profitability": "", "solvency": "", "efficiency": "", "risk": "",
        "report": "",
    })
    return {
        "metrics": metrics,
        "sections": {
            "盈利能力": result.get("profitability", ""),
            "偿债能力": result.get("solvency", ""),
            "营运能力": result.get("efficiency", ""),
            "风险排查": result.get("risk", ""),
        },
        "report": result.get("report", ""),
    }
