"""记账工具：让 Agent 能把一笔账记进账本。

复式记账规则（在这里用代码保证，而不是让 LLM 自由发挥）：
- 支出：借「费用科目」（费用增加记借方），贷「库存现金/银行存款」（资产减少记贷方）
- 收入：借「库存现金/银行存款」，贷「收入科目」

这个借贷规则用代码写死，保证每笔账的借贷方向永远正确——
这是财经专业背景的价值所在，也是普通 AI 记账产品最容易做错的地方。
"""

from __future__ import annotations

from datetime import datetime

from langchain.tools import tool
from sqlalchemy import select

from app.core.accounts import EXPENSE_CATEGORIES
from app.db.models import LedgerEntry
from app.db.session import SessionLocal


def _today() -> str:
    """取今天的日期。日期是确定性信息，必须由代码给出，而不是让模型猜。"""
    return datetime.now().strftime("%Y-%m-%d")


def _save_entry(date: str, amount: float, description: str, category: str,
                entry_type: str, debit: str, credit: str) -> str:
    """把一条账目写进数据库，返回给 LLM 看的结果描述。"""
    with SessionLocal() as db:
        entry = LedgerEntry(
            date=date,
            amount=amount,
            description=description,
            category=category,
            entry_type=entry_type,
            debit_account=debit,
            credit_account=credit,
        )
        db.add(entry)
        db.commit()
    return f"已记账：{date} {description} {amount:.2f} 元 → 借:{debit} 贷:{credit}"


@tool
def record_expense(amount: float, description: str, category: str,
                   date: str | None = None, payment_method: str = "库存现金") -> str:
    """记一笔支出。

    当用户说"花了多少钱买了/干了什么"时，调用本工具记账。
    本工具会自动按复式记账生成借贷分录：借「费用科目」，贷「支付方式」。

    Args:
        amount: 金额（正数，单位元）。
        description: 摘要，如"打车""买办公用品"。
        category: 费用科目，必须是：交通费/餐饮费/办公费/差旅费/通讯费/房租/水电费。
        date: 记账日期，格式 YYYY-MM-DD。用户没说明日期就传空（None），工具会用今天。
        payment_method: 支付方式，默认"库存现金"，也可以是"银行存款"。
    """
    if category not in EXPENSE_CATEGORIES:
        return f"科目 {category} 不在可选范围内。可选：{'/'.join(EXPENSE_CATEGORIES)}"
    if amount <= 0:
        return "金额必须大于 0。"
    date = date or _today()  # 没传日期就用今天，由代码保证，不让模型编
    # 支出：借 费用科目，贷 支付方式
    return _save_entry(date, amount, description, category, "expense", category, payment_method)


@tool
def record_income(amount: float, description: str, category: str,
                  date: str | None = None, receive_method: str = "库存现金") -> str:
    """记一笔收入。

    当用户说"收到/赚了多少钱"时调用。借贷分录：借「收款方式」，贷「收入科目」。

    Args:
        amount: 金额（正数，单位元）。
        description: 摘要，如"8月工资"。
        category: 收入科目，如"工资收入""营业收入"。
        date: 日期，格式 YYYY-MM-DD。用户没说明就传空，工具会用今天。
        receive_method: 收款方式，默认"库存现金"，也可"银行存款"。
    """
    if amount <= 0:
        return "金额必须大于 0。"
    date = date or _today()
    # 收入：借 收款方式，贷 收入科目
    return _save_entry(date, amount, description, category, "income", receive_method, category)


@tool
def record_with_voucher(amount: float, description: str, voucher: str,
                        entry_type: str = "expense",
                        counterparty_name: str = "",
                        date: str | None = None,
                        payment: str = "银行存款") -> str:
    """在聊天里凭证记账（**必须有凭证文件**）。

    只有当用户在聊天框上传了凭证文件时才能用——没上传凭证一律拒绝，
    因为记账必须有原始凭证（白条入账税务不认）。

    登记后状态是「待审核」，要等会计审核通过才计入报表——
    这只是出纳的另一个录入入口，不绕过任何流程。

    Args:
        amount: 金额（正数）。
        description: 摘要，如"买办公用品"。
        voucher: 用户上传的凭证文件名（系统会告诉你）。
        entry_type: expense（付款）/ income（收款）。
        counterparty_name: 往来单位名称（发票上的销售方/购买方）。
        date: 日期 YYYY-MM-DD，没说就传空。
        payment: 收付款方式。
    """
    from pathlib import Path

    from app.db.models import LedgerEntry
    from app.db.session import SessionLocal as _Session

    # ---- 凭证校验：没凭证不许记 ----
    if not voucher or not voucher.strip():
        return ("不能记账：没有凭证。记账必须有发票/收据/回单——\n"
                "请点聊天框的 📎 上传凭证，然后再说一次。")
    safe = Path(voucher).name
    if not (Path("data/attachments") / safe).is_file():
        return (f"不能记账：找不到凭证文件「{safe}」。\n"
                "请重新上传凭证再试。")

    if amount <= 0:
        return "金额必须大于 0。"
    if entry_type not in ("expense", "income"):
        return "收付方向只能是 expense（付款）或 income（收款）。"

    # 往来单位：填了名字就自动匹配/建档
    cp_id = None
    if counterparty_name.strip():
        from app.services import counterparty_service as cps
        hit = cps.find_by_name(counterparty_name)
        if hit:
            cp_id = hit.id
        else:
            created = cps.create(
                name=counterparty_name.strip(),
                kind="customer" if entry_type == "income" else "supplier",
            )
            if created.get("ok"):
                cp_id = created["counterparty"]["id"]

    entry_date = date or _today()
    with _Session() as db:
        row = LedgerEntry(
            date=entry_date, amount=round(amount, 2),
            description=description.strip()[:100],
            category="",            # 科目由会计审核时确定
            entry_type=entry_type,
            debit_account="", credit_account="",
            counterparty_id=cp_id,
            attachment=safe,
            payment=payment,
            status="pending",       # 待审核——不直接入账
        )
        db.add(row)
        db.commit()
        db.refresh(row)

    direction = "收款" if entry_type == "income" else "付款"
    return (f"已登记{direction}：{entry_date} {row.description} {row.amount:,.2f}元"
            f"（凭证已附）\n状态：**待会计审核** —— 请到「📚 智能会计」审核入账。")


@tool
def record_asset_purchase(amount: float, item: str,
                          date: str | None = None,
                          payment_method: str = "银行存款") -> str:
    """记一笔固定资产购置（买车、买设备、买房产等）。

    【重要】买大件资产不是「费用」，不能在 record_expense 里记。
    会计上这是资产之间的转换：银行存款 变成 固定资产，
    不影响当期利润。用本工具记账才是对的。

    当用户说「买车/买设备/买电脑/买房子花了多少钱」时，调用本工具。

    Args:
        amount: 金额（正数，单位元）。
        item: 买了什么，如"汽车""办公设备""生产设备"。
        date: 日期 YYYY-MM-DD。没说就传空，工具用今天。
        payment_method: 支付方式，默认"银行存款"。
    """
    if amount <= 0:
        return "金额必须大于 0。"
    date = date or _today()
    desc = f"购置固定资产-{item}"
    # 借 固定资产（资产增加）贷 银行存款（资产减少）—— 资产内部转换，不是费用
    return _save_entry(date, amount, desc, "固定资产", "asset",
                       "固定资产", payment_method)


@tool
def query_entries(category: str | None = None, start_date: str | None = None,
                  end_date: str | None = None,
                  entry_type: str | None = None) -> str:
    """查询账目，返回汇总（收入/支出分开）和部分明细。

    用户问"花了多少""收入多少""某类支出多少""某段时间的账"时，调用本工具。

    Args:
        category: 按科目筛选（如"房租"）。不填查全部。
        start_date: 起始日期 YYYY-MM-DD。不填则不限制。
        end_date: 结束日期 YYYY-MM-DD。不填则不限制。
        entry_type: 只看收入填"income"，只看支出填"expense"。不填则都查。
    """
    with SessionLocal() as db:
        stmt = select(LedgerEntry).where(LedgerEntry.status == "approved")
        if category:
            stmt = stmt.where(LedgerEntry.category == category)
        if start_date:
            stmt = stmt.where(LedgerEntry.date >= start_date)
        if end_date:
            stmt = stmt.where(LedgerEntry.date <= end_date)
        if entry_type:
            stmt = stmt.where(LedgerEntry.entry_type == entry_type)
        rows = db.scalars(stmt.order_by(LedgerEntry.date)).all()

    if not rows:
        return "没有查到符合条件的账目。"

    # 收入、支出必须分开统计（之前混在一起加，是错的）
    income = sum(r.amount for r in rows if r.entry_type == "income")
    expense = sum(r.amount for r in rows if r.entry_type == "expense")

    # 按科目汇总支出，方便回答"哪类花得多"
    by_cat: dict[str, float] = {}
    for r in rows:
        if r.entry_type == "expense":
            by_cat[r.category] = by_cat.get(r.category, 0) + r.amount
    cat_lines = [f"  {k}: {v:.2f}元" for k, v in sorted(by_cat.items(), key=lambda x: -x[1])]

    summary = (
        f"共 {len(rows)} 笔\t收入合计 {income:.2f} 元\t"
        f"支出合计 {expense:.2f} 元\t净额 {income - expense:.2f} 元"
    )
    if cat_lines:
        summary += "\n支出按科目：\n" + "\n".join(cat_lines)

    # 只附最近 10 笔明细，避免把 400+ 笔全塞进上下文
    recent = rows[-10:]
    detail = "\n".join(f"  {r.date} {r.description} {r.amount:.2f}元（{r.category}）"
                      for r in recent)
    return f"{summary}\n\n最近 {len(recent)} 笔明细：\n{detail}"
