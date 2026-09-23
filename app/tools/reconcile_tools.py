"""对账工具：把 LangGraph 对账流程暴露给 Agent。"""

from __future__ import annotations

from langchain.tools import tool
from sqlalchemy import select

from app.agents.reconcile import reconcile_entries
from app.db.models import LedgerEntry
from app.db.session import SessionLocal


@tool
def reconcile_month(month: str | None = None) -> str:
    """对账：核对账目，发现大额支出、重复记账、信息缺失等异常。

    当用户说"对账""检查账目有没有问题""月底核对"时，调用本工具。
    会扫描账本里的所有账目，返回异常清单或"未发现异常"。

    Args:
        month: 要核对的月份，格式 YYYY-MM（如 2026-09）。不填则核对全部账目。
    """
    with SessionLocal() as db:
        stmt = select(LedgerEntry)
        if month:
            stmt = stmt.where(LedgerEntry.date.like(f"{month}%"))
        rows = db.scalars(stmt).all()

    if not rows:
        return "账本里没有可核对的账目。"

    entries = [
        {
            "date": r.date,
            "amount": r.amount,
            "description": r.description,
            "category": r.category,
            "entry_type": r.entry_type,
        }
        for r in rows
    ]
    return reconcile_entries(entries)
