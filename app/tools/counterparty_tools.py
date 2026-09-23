"""往来查询工具：按客户/供应商查所有业务往来。

为什么需要它：摘要里记着"销售商品-石家庄恒信商贸"，但按科目/日期筛选的工具
查不到它。企业实际工作中，"这个客户一年跟我做了多少生意、付款爽不爽快"
是最常问的问题之一。
"""

from __future__ import annotations

from collections import defaultdict

from langchain.tools import tool
from sqlalchemy import select

from app.db.models import Counterparty, LedgerEntry
from app.db.session import SessionLocal


@tool
def query_counterparty(name: str) -> str:
    """查询与某个客户或供应商的所有业务往来，并给出往来情况分析。

    当用户问「XX公司跟我们做了多少生意」「查一下XX的往来」「XX这个客户怎么样」
    「XX供应商的合作情况」时，调用本工具。

    优先按「往来单位档案」精确匹配（名字写错也能对上），
    档案里没有的再退回按摘要关键词模糊搜索。

    Args:
        name: 客户或供应商名称（可以是简称，如"恒信"）。
    """
    if not name or not name.strip():
        return "请提供要查询的客户或供应商名称。"

    keyword = name.strip()
    with SessionLocal() as db:
        # 1. 先查往来单位档案（精确/模糊都能匹配）
        cps = db.scalars(select(Counterparty)).all()
        hit = next((c for c in cps if keyword in c.name), None)
        if hit is None:
            hit = next((c for c in cps if c.name in keyword), None)

        if hit is not None:
            rows = db.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.counterparty_id == hit.id,
                       LedgerEntry.status == "approved")
                .order_by(LedgerEntry.date)
            ).all()
            matched = list(rows)
            matched_name = hit.name
            kind_cn = "客户" if hit.kind == "customer" else "供应商"
        else:
            # 2. 档案里没有 → 退回按摘要模糊搜索
            rows = db.scalars(select(LedgerEntry)).all()
            matched = [r for r in rows
                       if keyword in (r.description or "") and r.status == "approved"]
            matched_name = keyword
            kind_cn = ""

    if not matched:
        return f"没有找到与「{keyword}」相关的业务往来。"

    return _format(name=matched_name, kind_cn=kind_cn, matched=matched)


def _format(name: str, kind_cn: str, matched: list) -> str:
    """把往来明细整理成给模型看的文本。"""
    total = sum(r.amount for r in matched)
    n = len(matched)
    dates = [r.date for r in matched]

    income = sum(r.amount for r in matched if r.entry_type == "income")
    expense = sum(r.amount for r in matched if r.entry_type == "expense")

    by_cat: dict[str, float] = defaultdict(float)
    for r in matched:
        by_cat[r.category] += r.amount

    # 挂账情况：客户看应收，供应商看应付
    receivable = sum(r.amount for r in matched if r.debit_account == "应收账款")
    payable = sum(r.amount for r in matched if r.credit_account == "应付账款")
    cash_in = sum(r.amount for r in matched if r.debit_account in ("银行存款", "库存现金"))

    title = f"【{name}】" + (f"（{kind_cn}）" if kind_cn else "")
    lines = [
        f"{title} 往来总览",
        f"  交易笔数：{n} 笔",
        f"  时间跨度：{dates[0]} ~ {dates[-1]}",
        f"  交易总额：{total:,.2f} 元（平均每笔 {total / n:,.2f} 元）",
    ]
    if income:
        lines.append(f"  我方收入：{income:,.2f} 元")
    if expense:
        lines.append(f"  我方支出：{expense:,.2f} 元")

    lines.append("")
    lines.append("  涉及科目：")
    for k, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"    {k}：{v:,.2f} 元")

    if receivable or cash_in:
        lines.append("")
        lines.append("  结算情况（销售侧）：")
        if receivable:
            denom = receivable + cash_in
            pct = receivable / denom * 100 if denom else 0
            lines.append(f"    赊销（挂应收账款）：{receivable:,.2f} 元，占 {pct:.0f}%")
        if cash_in:
            denom = receivable + cash_in
            pct = cash_in / denom * 100 if denom else 0
            lines.append(f"    现结（银行/现金）：{cash_in:,.2f} 元，占 {pct:.0f}%")

    if payable:
        lines.append("")
        lines.append(f"  结算情况（采购侧）：赊购（挂应付账款）{payable:,.2f} 元")

    recent = matched[-5:]
    lines.append("")
    lines.append(f"  最近 {len(recent)} 笔明细：")
    for r in recent:
        lines.append(f"    {r.date} {r.description} {r.amount:,.2f} 元（{r.category}）")

    return "\n".join(lines)
