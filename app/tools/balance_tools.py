"""余额查询工具：让 Agent 能回答"我还有多少钱"这类问题。

和 query_entries 的区别（重要）：
- query_entries 查的是「流水」——这段时间收了多少、花了多少
- 本工具算的是「余额」——账户上现在还剩多少

余额 = 期初 + 各笔分录的借方 − 贷方。这是会计里「记账」和「报表」两件事的后半件。
"""

from __future__ import annotations

from collections import defaultdict

from langchain.tools import tool
from sqlalchemy import select

from app.db.models import LedgerEntry
from app.db.session import SessionLocal

# 这些词是「概念」不是账户名，模型容易误传进来
_CONCEPT_WORDS = {"流动资金", "现金", "钱", "余额", "总余额", "资金", "可用资金", "现金余额"}


def _balances() -> dict[str, float]:
    """算各账户余额。只算【已入账】的账目——待审核的还没进账。"""
    with SessionLocal() as db:
        rows = [r for r in db.scalars(select(LedgerEntry)).all()
                if r.status == "approved"]
    bal: dict[str, float] = defaultdict(float)
    for r in rows:
        bal[r.debit_account] += r.amount
        bal[r.credit_account] -= r.amount
    return bal


def _summary(bal: dict[str, float]) -> str:
    from app.core.accounts import ASSET_ACCOUNTS, LIABILITY_ACCOUNTS

    cash = bal.get("库存现金", 0.0)
    bank = bal.get("银行存款", 0.0)
    lines = [
        f"库存现金：{cash:,.2f} 元",
        f"银行存款：{bank:,.2f} 元",
        f"【流动资金合计（现金 + 银行）】：{cash + bank:,.2f} 元",
        "",
        "其他资产与负债：",
    ]
    # 只列资产/负债类（这些才叫"余额"）。负债是贷方余额，取反显示成正数。
    listed = 0
    for name in ASSET_ACCOUNTS:
        v = bal.get(name, 0.0)
        if name in ("库存现金", "银行存款") or abs(v) < 0.005:
            continue
        lines.append(f"  {name}（资产）：{v:,.2f} 元")
        listed += 1
    for name in LIABILITY_ACCOUNTS:
        v = bal.get(name, 0.0)
        if abs(v) < 0.005:
            continue
        lines.append(f"  {name}（负债）：{-v:,.2f} 元")
        listed += 1
    if listed == 0:
        lines.append("  （无）")
    return "\n".join(lines)


@tool
def get_account_balance(account: str | None = None) -> str:
    """查询账户余额：手头现在还剩多少钱。

    当用户问「还有多少钱」「流动资金多少」「现金余额」「银行余额」「账上还剩多少」时，
    调用本工具。

    【重要】account 参数只在用户明确说出某个具体账户名时才传，
    比如「银行存款」「库存现金」「应收账款」。
    像「流动资金」「余额」「钱」这类词是**概念不是账户名**，一律不要传 account，
    留空即可（留空会自动返回流动资金合计和全部账户余额）。

    Args:
        account: 具体账户名（如"银行存款"）。不填则返回流动资金合计 + 全部账户余额。
    """
    bal = _balances()
    if not bal:
        return "账本里没有任何账目。"

    # 容错：模型可能把「流动资金」这类概念词当账户名传进来，那就返回汇总
    if account and account.strip() not in _CONCEPT_WORDS:
        value = bal.get(account)
        if value is not None:
            return f"{account} 当前余额：{value:,.2f} 元"
        # 没找到这个账户，也给出汇总，避免答非所问
        available = "、".join(sorted(k for k, v in bal.items() if abs(v) > 0.005))
        return f"没有「{account}」这个账户。以下是全部账户余额：\n{_summary(bal)}\n\n现有账户：{available}"

    return _summary(bal)
