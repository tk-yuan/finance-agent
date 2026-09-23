"""删除/撤销工具：只能动【待审核】的单据。

已入账的账目不能通过聊天删除——那需要走会计的反审核流程。
这是「出纳管钱、会计管账」分离的延伸：谁也不能绕过流程改账。
"""

from __future__ import annotations

from langchain.tools import tool
from sqlalchemy import select

from app.db.models import LedgerEntry
from app.db.session import SessionLocal

_LOCKED_MSG = (
    "这笔已经入账了，不能直接删除。\n"
    "已入账的账目需要走会计的反审核流程（在「📚 智能会计」里处理）。"
)


def _guarded_delete(row: LedgerEntry, db) -> str:
    """只允许删待审核/已驳回的单据。"""
    if row.status == "approved":
        return f"「{row.description}」{_LOCKED_MSG}"
    info = f"{row.date} {row.description} {row.amount:.2f}元（{row.category or '未定科目'}）"
    db.delete(row)
    db.commit()
    return f"已撤销：{info}"


@tool
def delete_last_entry() -> str:
    """撤销最近登记的一笔单据。

    当用户说「刚才那笔记错了」「删掉上一笔」「撤销刚才的记账」时，调用本工具。
    只能撤销**待审核**的单据；已经入账的要走会计反审核。
    """
    with SessionLocal() as db:
        row = db.scalars(
            select(LedgerEntry).order_by(LedgerEntry.id.desc()).limit(1)
        ).first()
        if row is None:
            return "账本里没有单据可撤销。"
        return _guarded_delete(row, db)


@tool
def find_entries(keyword: str) -> str:
    """按关键词查找单据，返回编号和状态，便于确认要处理哪一笔。

    Args:
        keyword: 关键词，如"买车""打车""房租"。
    """
    with SessionLocal() as db:
        rows = db.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.description.like(f"%{keyword}%"))
            .order_by(LedgerEntry.id.desc())
            .limit(20)
        ).all()
    if not rows:
        return f"没找到含「{keyword}」的单据。"
    lines = [
        f"  编号{r.id}：{r.date} {r.description} {r.amount:.2f}元"
        f"（{r.category or '未定科目'}）— {r.as_dict()['status_cn']}"
        for r in rows
    ]
    return f"找到 {len(rows)} 笔：\n" + "\n".join(lines)


@tool
def delete_entry_by_id(entry_id: int) -> str:
    """按编号撤销单据（编号可用 find_entries 查）。

    只能撤销**待审核**的单据。

    Args:
        entry_id: 单据编号。
    """
    with SessionLocal() as db:
        row = db.get(LedgerEntry, entry_id)
        if row is None:
            return f"找不到编号 {entry_id} 的单据。"
        return _guarded_delete(row, db)
