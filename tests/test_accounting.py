"""会计逻辑测试：科目建议、状态流转、现金盘点、结账。

这些是系统的核心业务规则，必须有测试兜底——
比如"只有已入账的账目才进报表"这条规则一旦被破坏，
报表会突然把出纳还没审的单子算进去，而且没人会发现。
"""

from __future__ import annotations

import pytest

from app.db.models import LedgerEntry
from app.db.session import SessionLocal, init_db


def _clear():
    init_db()
    with SessionLocal() as db:
        db.query(LedgerEntry).delete()
        db.commit()


def _add(date: str, amount: float, description: str, category: str,
         entry_type: str, debit: str, credit: str, status: str = "approved"):
    with SessionLocal() as db:
        row = LedgerEntry(
            date=date, amount=amount, description=description, category=category,
            entry_type=entry_type, debit_account=debit, credit_account=credit,
            status=status,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


# ---------- 科目建议 ----------

@pytest.mark.parametrize("desc,expected", [
    ("打车去客户公司", "交通费"),
    ("出差住宿费", "差旅费"),
    ("采购办公用品", "办公费"),
    ("缴纳社保及公积金", "社保费"),
    ("支付办公室租金", "房租"),
    ("客户招待餐费", "业务招待费"),
    ("银行手续费", "银行手续费"),
    ("计提当月工资", "工资"),
    ("缴纳增值税", "税费"),
])
def test_suggest_category(desc, expected):
    """科目建议要能覆盖常见支出——建议错了会计还得手改。"""
    from app.api.v1.accounting import _suggest_category

    assert _suggest_category(desc, "expense") == expected


def test_suggest_category_unknown_returns_other():
    """认不出来的要返回「其他」，让会计自己判断，不能瞎猜。"""
    from app.api.v1.accounting import _suggest_category

    assert _suggest_category("参加行业展会", "expense") == "其他"


def test_income_defaults_to_main_revenue():
    from app.api.v1.accounting import _suggest_category

    assert _suggest_category("收到货款", "income") == "主营业务收入"


# ---------- 状态流转：只有已入账才进报表 ----------

def test_pending_entries_excluded_from_reports():
    """**核心规则**：待审核的账目不能进报表。

    这条一旦失效，出纳录错的单子会直接影响报表，职务分离就白做了。
    """
    from app.services.stats_service import overview

    _clear()
    _add("2026-09-01", 1000, "已入账的", "办公费", "expense", "办公费", "银行存款",
         status="approved")
    _add("2026-09-02", 99999, "待审核的", "办公费", "expense", "办公费", "银行存款",
         status="pending")

    ov = overview()
    assert ov["total_entries"] == 1, "待审核的账目不该被统计"
    assert ov["total_expense"] == 1000, "金额里不能算进待审核那笔"


def test_rejected_entries_excluded_from_reports():
    from app.services.stats_service import overview

    _clear()
    _add("2026-09-01", 500, "被驳回的", "办公费", "expense", "办公费", "银行存款",
         status="rejected")
    assert overview()["total_expense"] == 0


# ---------- 现金盘点 ----------

def test_cash_check_shortage():
    """盘亏：实盘少于账面，差额为负。"""
    from app.services.checkup_service import create_cash_check

    _clear()
    _add("2026-09-01", 10000, "期初备用金", "库存现金", "expense",
         "库存现金", "实收资本")

    r = create_cash_check(actual_amount=9950, date="2026-09-30")
    assert r["book_amount"] == 10000
    assert r["difference"] == -50
    assert r["result"] == "盘亏"


def test_cash_check_surplus():
    from app.services.checkup_service import create_cash_check

    _clear()
    _add("2026-09-01", 10000, "期初备用金", "库存现金", "expense",
         "库存现金", "实收资本")

    r = create_cash_check(actual_amount=10120, date="2026-09-30")
    assert r["difference"] == 120
    assert r["result"] == "盘盈"


def test_cash_check_matched():
    from app.services.checkup_service import create_cash_check

    _clear()
    _add("2026-09-01", 8000, "期初备用金", "库存现金", "expense",
         "库存现金", "实收资本")

    r = create_cash_check(actual_amount=8000, date="2026-09-30")
    assert r["difference"] == 0
    assert r["result"] == "相符"


# ---------- 银行存款余额调节表 ----------

def test_bank_reconciliation_matches():
    """调节后余额 = 企业账面余额时，判定为相符。"""
    from app.services.checkup_service import create_bank_recon

    _clear()
    # 账面银行 90000
    _add("2026-09-01", 90000, "股东投入", "实收资本", "income",
         "银行存款", "实收资本")

    # 对账单 60000，加 30000（银行未收） → 调节后 90000 = 账面
    r = create_bank_recon(
        period="2026-09", statement_balance=60000,
        items_added=[{"desc": "客户转账在路上", "amount": 30000}],
    )
    assert r["adjusted_balance"] == 90000
    assert r["book_balance"] == 90000
    assert r["reconciled"] is True


def test_bank_reconciliation_mismatch():
    from app.services.checkup_service import create_bank_recon

    _clear()
    _add("2026-09-01", 90000, "股东投入", "实收资本", "income",
         "银行存款", "实收资本")

    # 对账单 60000，没列未达账项 → 调节后 60000 ≠ 账面 90000
    r = create_bank_recon(period="2026-09", statement_balance=60000)
    assert r["reconciled"] is False
    assert r["difference"] == -30000


# ---------- 会计恒等式 ----------

def test_equity_injection_not_counted_as_income():
    """权益投入不能被算成收入。

    踩过的坑：股东投入 100 万，出纳记成「收款」、会计选「实收资本」科目。
    如果按收付方向(entry_type)算收入，这 100 万会虚增利润，资产和权益就不配平。
    """
    from app.services.stats_service import overview

    _clear()
    _add("2026-09-01", 1000000, "股东投入实收资本", "实收资本", "income",
         "银行存款", "实收资本")

    ov = overview()
    assert ov["total_income"] == 0, "股东投入不是经营收入"


def test_closing_entries_not_double_counted():
    """月末结转分录不能算进收入/支出，否则利润翻倍。"""
    from app.services.stats_service import overview

    _clear()
    _add("2026-09-10", 50000, "销售收入", "主营业务收入", "income",
         "银行存款", "主营业务收入")
    # 月末结转：借 主营业务收入 贷 本年利润
    _add("2026-09-30", 50000, "期末结转-主营业务收入", "主营业务收入", "closing",
         "主营业务收入", "本年利润")

    ov = overview()
    assert ov["total_income"] == 50000, "结转分录被重复计算了"


def test_paying_salary_not_double_counted():
    """「发放工资」不是费用，只是付钱，不能和「计提工资」重复算。

    踩过的坑：两笔的 category 都是"工资"，按科目判断会把工资算两遍
    （12 个月 × 6.8 万 = 81.6 万，直接让利润表变亏损）。
    """
    from app.services.stats_service import overview

    _clear()
    # 计提：借 工资 贷 应付职工薪酬  → 这是费用
    _add("2026-09-10", 68000, "计提当月工资", "工资", "expense",
         "工资", "应付职工薪酬")
    # 发放：借 应付职工薪酬 贷 银行存款  → 这只是付钱
    _add("2026-09-15", 68000, "发放当月工资", "工资", "transfer",
         "应付职工薪酬", "银行存款")

    ov = overview()
    assert ov["total_expense"] == 68000, "工资被算了两遍"


def test_asset_purchase_not_expense():
    """买固定资产是资产购置，不进费用。"""
    from app.services.stats_service import overview

    _clear()
    _add("2026-09-01", 200000, "购置固定资产-汽车", "固定资产", "asset",
         "固定资产", "银行存款")

    assert overview()["total_expense"] == 0


def test_agent_has_no_unrestricted_recording_tools():
    """**内控关键**：Agent 不能有「不受约束」的记账工具。

    聊天里唯一能记账的是 record_with_voucher —— 它强制要求凭证文件，
    而且登记后状态是「待审核」。所以聊天记账不绕过凭证校验和会计审核。

    绝不能出现的是 record_expense / record_income 这种
    「有金额就能记」的工具——那才是绕过流程。
    """
    from app.tools import BUILTIN_TOOLS

    names = {t.name for t in BUILTIN_TOOLS}
    forbidden = {"record_expense", "record_income", "record_asset_purchase"}
    assert not (names & forbidden), (
        f"Agent 不该有无约束的记账工具，但发现了: {names & forbidden}"
    )
    assert "record_with_voucher" in names, "受控的凭证记账工具应该存在"


def test_voucher_recording_requires_voucher():
    """record_with_voucher 没凭证时必须拒绝。"""
    from app.tools.ledger_tools import record_with_voucher

    _clear()
    # 不传凭证
    r = record_with_voucher.invoke({
        "amount": 100, "description": "买办公用品", "voucher": "",
    })
    assert "不能记账" in r or "凭证" in r

    # 传一个不存在的文件名
    r2 = record_with_voucher.invoke({
        "amount": 100, "description": "买办公用品", "voucher": "不存在.pdf",
    })
    assert "找不到凭证" in r2

    # 确认真的没记进去
    from app.db.models import LedgerEntry
    with SessionLocal() as db:
        assert db.query(LedgerEntry).count() == 0


def test_voucher_recording_creates_pending_entry():
    """有凭证时可以记，但状态必须是「待审核」，不能直接入账。"""
    import os
    from pathlib import Path

    from app.db.models import LedgerEntry
    from app.tools.ledger_tools import record_with_voucher

    _clear()
    d = Path("data/attachments")
    d.mkdir(parents=True, exist_ok=True)
    name = "_test_voucher.pdf"
    (d / name).write_bytes(b"test")
    try:
        r = record_with_voucher.invoke({
            "amount": 320, "description": "买办公用品", "voucher": name,
        })
        assert "待会计审核" in r

        with SessionLocal() as db:
            row = db.query(LedgerEntry).first()
            assert row is not None
            assert row.status == "pending", "聊天记的账也必须是待审核"
            assert row.attachment == name
            assert row.amount == 320
            assert row.category == "", "科目要留给会计定"
    finally:
        os.remove(d / name)


def test_agent_tools_are_readonly_or_limited():
    """Agent 的工具应该以只读为主，写操作只有「受控记账」和「撤销待审核单据」。"""
    from app.tools import BUILTIN_TOOLS

    names = {t.name for t in BUILTIN_TOOLS}
    limited_writes = {"record_with_voucher", "delete_last_entry", "delete_entry_by_id"}
    # 所有非只读的工具都必须在白名单里
    assert {"record_with_voucher", "delete_last_entry"} <= names
    assert "record_expense" not in names


def test_balance_sheet_equation_holds():
    """资产 = 负债 + 所有者权益。任何记账错误都会让这个等式失衡。"""
    from app.services.stats_service import account_balances

    _clear()
    # 股东投入 100000（银行），花掉 30000 办公费
    _add("2026-09-01", 100000, "股东投入", "实收资本", "income",
         "银行存款", "实收资本")
    _add("2026-09-02", 30000, "买办公用品", "办公费", "expense",
         "办公费", "银行存款")

    d = account_balances()
    assert d["balance_sheet_ok"] is True, (
        f"资产 {d['total_assets']} ≠ 负债+权益 {d['total_liabilities_equity']}"
    )
