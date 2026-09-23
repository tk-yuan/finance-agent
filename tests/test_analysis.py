"""财务分析测试：指标计算。

指标必须由代码算准——让大模型算毛利率是不可靠的。
这里验证四个维度的计算逻辑。
"""

from __future__ import annotations

from app.db.models import LedgerEntry
from app.db.session import SessionLocal, init_db


def _clear():
    init_db()
    with SessionLocal() as db:
        db.query(LedgerEntry).delete()
        db.commit()


def _add(date, amount, description, category, entry_type, debit, credit,
         status="approved"):
    with SessionLocal() as db:
        db.add(LedgerEntry(
            date=date, amount=amount, description=description, category=category,
            entry_type=entry_type, debit_account=debit, credit_account=credit,
            status=status,
        ))
        db.commit()


def test_profitability_metrics():
    """毛利率、净利率要算对。"""
    from app.services.finance_analysis import profitability

    _clear()
    # 收入 100 万，成本 70 万，另有办公费 5 万
    _add("2026-09-01", 1_000_000, "销售收入", "主营业务收入", "income",
         "银行存款", "主营业务收入")
    _add("2026-09-02", 700_000, "采购成本", "主营业务成本", "expense",
         "主营业务成本", "银行存款")
    _add("2026-09-03", 50_000, "办公费", "办公费", "expense",
         "办公费", "银行存款")

    m = profitability()
    assert m["营业收入"] == 1_000_000
    assert m["毛利"] == 300_000
    assert m["毛利率"] == 30.0
    assert m["净利润"] == 250_000          # 100万 − 70万 − 5万
    assert m["净利率"] == 25.0


def test_solvency_metrics():
    """资产负债率、流动比率要算对。"""
    from app.services.finance_analysis import solvency

    _clear()
    # 资产：银行 100 万；负债：应付 20 万
    _add("2026-09-01", 1_000_000, "股东投入", "实收资本", "equity",
         "银行存款", "实收资本")
    _add("2026-09-02", 200_000, "赊购", "主营业务成本", "expense",
         "主营业务成本", "应付账款")

    m = solvency()
    assert m["资产总额"] == 1_000_000
    assert m["负债总额"] == 200_000
    assert m["资产负债率"] == 20.0
    assert m["流动比率"] == 5.0            # 100万 / 20万


def test_efficiency_metrics():
    """赊销占比要算对。"""
    from app.services.finance_analysis import efficiency

    _clear()
    # 赊销 60 万 + 现结 40 万 = 100 万
    _add("2026-09-01", 600_000, "赊销", "主营业务收入", "income",
         "应收账款", "主营业务收入")
    _add("2026-09-02", 400_000, "现结", "主营业务收入", "income",
         "银行存款", "主营业务收入")

    m = efficiency()
    assert m["赊销占比"] == 60.0
    assert m["现结占比"] == 40.0


def test_risk_detects_large_expense():
    """大额支出要被识别出来。"""
    from app.agents.reconcile import LARGE_AMOUNT
    from app.services.finance_analysis import risk

    _clear()
    _add("2026-09-01", LARGE_AMOUNT + 50_000, "异常大额采购", "主营业务成本",
         "expense", "主营业务成本", "银行存款")
    _add("2026-09-02", 1000, "正常支出", "办公费", "expense",
         "办公费", "银行存款")

    m = risk()
    assert m["大额支出笔数"] == 1
    assert m["大额支出金额"] == LARGE_AMOUNT + 50_000


def test_metrics_only_count_approved():
    """待审核的账目不能进分析——和报表口径一致。"""
    from app.services.finance_analysis import profitability

    _clear()
    _add("2026-09-01", 500_000, "已入账收入", "主营业务收入", "income",
         "银行存款", "主营业务收入", status="approved")
    _add("2026-09-02", 9_999_999, "待审核收入", "主营业务收入", "income",
         "银行存款", "主营业务收入", status="pending")

    assert profitability()["营业收入"] == 500_000
