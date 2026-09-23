"""企业账务数据生成器。

生成一家小型商贸公司一年的完整账务数据：销售、采购、工资、社保、房租、
水电、税费、报销、银行手续费。每笔都符合复式记账（借贷平衡）。

说明：企业真实账务数据属于商业机密、不会公开（这是全球通例）。
银行、用友/金蝶/SAP 等做系统测试时使用的都是这种「按规范生成的仿真数据」。
本生成器参照《小企业会计准则》的科目体系与业务流设计。

用法：
    python -m scripts.generate_enterprise_data          # 默认生成一年
    python -m scripts.generate_enterprise_data 3        # 生成 3 个月
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import LedgerEntry  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402

# 说明：本文件生成的是【仿真数据】，不指向任何真实企业。
# 客户/供应商名称为常见的商贸企业命名风格，仅用于演示。

CUSTOMERS = [
    "天津海河科技有限公司", "河北众鑫贸易公司", "北京华远建材有限公司",
    "天津开发区物流有限公司", "山东鲁通机械厂", "天津滨海电子有限公司",
    "石家庄恒信商贸", "廊坊兴达实业有限公司",
]
SUPPLIERS = [
    "浙江义乌小商品批发城", "广东东莞制造有限公司", "江苏南通纺织厂",
    "天津港进口贸易公司", "福建泉州供应商",
]
EMPLOYEES = ["张伟", "李娜", "王强", "刘洋", "陈静", "赵磊", "孙悦"]

MONTHLY_RENT = 12000.0
MONTHLY_SALARY_TOTAL = 68000.0


def _d(year: int, month: int, day: int) -> str:
    """安全地构造日期（处理不同月份天数）。"""
    import calendar

    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last)).isoformat()


def generate(year_months: list[tuple[int, int]], seed: int = 42) -> list[dict]:
    """生成账务数据。year_months 是 [(年,月), ...] 列表。

    模拟的是一家贸易公司的一年经营：
      成立投入 → 日常购销 → 月末回款/付款 → 各项费用
    其中应收、应付账款每月会回收/支付一部分，模拟真实的账期。
    """
    rng = random.Random(seed)
    entries: list[dict] = []
    ar = 0.0  # 应收账款余额（客户欠我们的）
    ap = 0.0  # 应付账款余额（我们欠供应商的）

    def add(date_str, amount, desc, category, etype, debit, credit):
        entries.append({
            "date": date_str, "amount": round(amount, 2), "description": desc,
            "category": category, "entry_type": etype,
            "debit_account": debit, "credit_account": credit,
        })

    for year, month in year_months:
        # ---- 0. 创业第一天：股东投入 ----
        # 公司从"有钱"开始：银行 100 万 + 备用金 2 万，来源是股东实收资本。
        # 没有这一笔，公司的钱就是凭空冒出来的，库存现金会算成负数。
        if (year, month) == year_months[0]:
            add(_d(year, month, 1), 1_000_000.0, "股东投入实收资本", "实收资本",
                "equity", "银行存款", "实收资本")
            add(_d(year, month, 1), 20_000.0, "期初备用金", "库存现金",
                "equity", "库存现金", "实收资本")

        # ---- 1. 销售收入：每月 15~25 笔 ----
        for _ in range(rng.randint(15, 25)):
            day = rng.randint(1, 28)
            amount = round(rng.uniform(3000, 48000), 2)
            customer = rng.choice(CUSTOMERS)
            if rng.random() < 0.6:          # 60% 赊销
                debit = "应收账款"
                ar += amount
            else:                            # 40% 现结
                debit = "银行存款"
            add(_d(year, month, day), amount, f"销售商品-{customer}", "主营业务收入",
                "income", debit, "主营业务收入")

        # ---- 2. 采购成本：每月 3~5 笔 ----
        for _ in range(rng.randint(3, 5)):
            day = rng.randint(1, 26)
            amount = round(rng.uniform(60000, 150000), 2)
            supplier = rng.choice(SUPPLIERS)
            if rng.random() < 0.7:          # 70% 赊购
                credit = "应付账款"
                ap += amount
            else:
                credit = "银行存款"
            add(_d(year, month, day), amount, f"采购商品-{supplier}", "主营业务成本",
                "expense", "主营业务成本", credit)

        # ---- 3. 月末回款：收回应收账款的大部分 ----
        # 相当于平均一个多月的账期。不做这一步，应收账款会只增不减，
        # 一年下来会累积到远超收入的不合理数字。
        if ar > 0:
            collect = round(ar * 0.85, 2)
            add(_d(year, month, 26), collect, "收回销售货款", "应收账款",
                "transfer", "银行存款", "应收账款")
            ar -= collect

        # ---- 4. 月末付款：支付应付账款的大部分 ----
        if ap > 0:
            pay = round(ap * 0.85, 2)
            add(_d(year, month, 27), pay, "支付供应商货款", "应付账款",
                "transfer", "应付账款", "银行存款")
            ap -= pay

        # ---- 5. 工资：每月计提 + 发放 ----
        # 会计说明（两笔都不能少，但性质不同）：
        #   计提：借「工资(费用)」贷「应付职工薪酬(负债)」——这笔是【费用】
        #   发放：借「应付职工薪酬」贷「银行存款」——这笔只是【清偿负债】，
        #         属于账户间转移，记成 transfer，否则工资会被当成费用算两遍
        add(_d(year, month, 10), MONTHLY_SALARY_TOTAL, "计提当月工资", "工资",
            "expense", "工资", "应付职工薪酬")
        add(_d(year, month, 15), MONTHLY_SALARY_TOTAL, "发放当月工资", "工资",
            "transfer", "应付职工薪酬", "银行存款")

        # ---- 6. 社保公积金：每月 1 次 ----
        add(_d(year, month, 15), round(MONTHLY_SALARY_TOTAL * 0.28, 2),
            "缴纳社保及公积金", "社保费", "expense", "社保费", "银行存款")

        # ---- 7. 房租：每月 1 次 ----
        add(_d(year, month, 5), MONTHLY_RENT, "支付办公室租金", "房租",
            "expense", "房租", "银行存款")

        # ---- 8. 水电费：每月 1 次 ----
        add(_d(year, month, 20), round(rng.uniform(1200, 3800), 2),
            "支付水电费", "水电费", "expense", "水电费", "银行存款")

        # ---- 9. 增值税：每月 1 次 ----
        add(_d(year, month, 25), round(rng.uniform(6000, 22000), 2),
            "缴纳增值税", "税费", "expense", "税费", "银行存款")

        # ---- 10. 员工报销：每月 3~8 笔 ----
        for _ in range(rng.randint(3, 8)):
            day = rng.randint(1, 27)
            kind = rng.choice([
                ("差旅费", "出差报销", (800, 6000)),
                ("办公费", "采购办公用品", (100, 1500)),
                ("业务招待费", "客户招待餐费", (500, 4000)),
                ("通讯费", "话费报销", (100, 600)),
                ("交通费", "市内交通费", (50, 800)),
            ])
            cat, desc, (lo, hi) = kind
            who = rng.choice(EMPLOYEES)
            add(_d(year, month, day), round(rng.uniform(lo, hi), 2),
                f"{desc}-{who}", cat, "expense", cat, "库存现金")

        # ---- 11. 提取备用金：每月从银行取现补充现金 ----
        # 不做这一步，报销只出不进，库存现金会变成负数
        add(_d(year, month, 3), 20000.0, "提取备用金", "库存现金",
            "transfer", "库存现金", "银行存款")

        # ---- 12. 银行手续费：每月 1~2 笔 ----
        for _ in range(rng.randint(1, 2)):
            add(_d(year, month, rng.randint(1, 28)), round(rng.uniform(20, 180), 2),
                "银行手续费", "银行手续费", "expense", "银行手续费", "银行存款")

    return entries


def inject_anomalies(entries: list[dict], seed: int = 7) -> list[dict]:
    """故意注入几笔典型异常，用于演示对账功能。

    真实企业的账本里，重复付款、异常大额采购、摘要缺失都是常见问题。
    干净的数据测不出对账能力，所以要造几笔「有问题」的。
    """
    rng = random.Random(seed)
    if not entries:
        return entries

    expenses = [e for e in entries if e["entry_type"] == "expense"]
    if not expenses:
        return entries

    # 异常1：重复付款（同一笔采购记了两次）
    dup = rng.choice(expenses)
    entries.append(dict(dup))

    # 异常2：异常大额采购（远超日常水平，但未到让公司亏损的程度）
    # 注意用银行付款——现实中 25 万的采购不可能走现金，否则库存现金会变负数
    big = dict(rng.choice(expenses))
    big["amount"] = 250000.0
    big["description"] = f"紧急采购-{rng.choice(SUPPLIERS)}"
    big["credit_account"] = "银行存款"
    entries.append(big)

    # 异常3：摘要缺失（记账时没写清楚）
    vague = dict(rng.choice(expenses))
    vague["description"] = "-"
    vague["amount"] = round(rng.uniform(2000, 8000), 2)
    entries.append(vague)

    return sorted(entries, key=lambda x: x["date"])


def _month_range(months: int) -> list[tuple[int, int]]:
    """从当前月往前推 N 个月。"""
    today = date.today()
    result = []
    y, m = today.year, today.month
    for _ in range(months):
        result.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(result))


def main() -> None:
    months = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    init_db()

    data = generate(_month_range(months))
    data = inject_anomalies(data)  # 注入几笔异常，供对账演示
    with SessionLocal() as db:
        for d in data:
            db.add(LedgerEntry(**d))
        db.commit()

    income = sum(d["amount"] for d in data if d["entry_type"] == "income")
    expense = sum(d["amount"] for d in data if d["entry_type"] == "expense")
    print(f"✓ 已生成 {len(data)} 笔账务（{months} 个月）")
    print(f"  收入合计 {income:,.2f} 元")
    print(f"  支出合计 {expense:,.2f} 元")
    print(f"  净额     {income - expense:,.2f} 元")


if __name__ == "__main__":
    main()
