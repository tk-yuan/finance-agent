"""记账 + 对账工具测试（纯规则，不依赖 LLM，快且稳定）。"""

from __future__ import annotations

from app.db.session import SessionLocal, init_db
from app.db.models import LedgerEntry
from app.tools.ledger_tools import record_expense
from app.tools.reconcile_tools import reconcile_month


def _clear():
    init_db()
    with SessionLocal() as db:
        db.query(LedgerEntry).delete()
        db.commit()


def test_record_expense_creates_debit_credit():
    """记账应生成正确的借贷分录。"""
    _clear()
    result = record_expense.invoke({"amount": 30, "description": "打车", "category": "交通费"})
    assert "借:交通费" in result
    assert "贷:库存现金" in result
    with SessionLocal() as db:
        rows = db.query(LedgerEntry).all()
        assert len(rows) == 1
        assert rows[0].debit_account == "交通费"
        assert rows[0].credit_account == "库存现金"


def test_record_expense_rejects_bad_category():
    """非法科目必须被拒绝。"""
    _clear()
    result = record_expense.invoke({"amount": 30, "description": "打车", "category": "娱乐费"})
    assert "不在可选范围" in result


def test_record_expense_rejects_nonpositive_amount():
    """金额必须大于 0。"""
    _clear()
    result = record_expense.invoke({"amount": 0, "description": "打车", "category": "交通费"})
    assert "大于 0" in result


def test_reconcile_detects_duplicate_and_large():
    """对账应检测出重复和大额异常。"""
    from app.agents.reconcile import LARGE_AMOUNT

    _clear()
    record_expense.invoke({"amount": 30, "description": "打车", "category": "交通费"})
    record_expense.invoke({"amount": 30, "description": "打车", "category": "交通费"})  # 重复
    # 大额：超过阈值
    record_expense.invoke({
        "amount": LARGE_AMOUNT + 1000, "description": "设备", "category": "办公费",
    })
    report = reconcile_month.invoke({})
    assert "重复" in report
    assert "大额" in report
