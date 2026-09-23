"""工具注册中心：Agent 能调用哪些工具。

**重要设计**：Agent（智能助手）是**只读 + 撤销待审核单据**的，
不能记账。

为什么：
    整个系统的内控基础是「出纳登记 → 会计审核」的单据流转。
    如果聊天助手能直接记账，就等于绕过了两道关卡：
      ① 凭证校验（没有凭证也能量记进去）
      ② 会计审核（不用审核就进报表）
    内控就白做了。

所以记账必须走「🧾 智能出纳」页面（表单直连数据库，不经过模型），
Agent 只负责查账、分析、以及对**待审核**单据的撤回。

（record_expense 等函数仍在 ledger_tools 里，供出纳模块和测试使用，
  只是不再暴露给 Agent。）
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.tools.balance_tools import get_account_balance
from app.tools.counterparty_tools import query_counterparty
from app.tools.delete_tools import delete_entry_by_id, delete_last_entry, find_entries
from app.tools.kb_tools import search_accounting_rules
from app.tools.ledger_tools import query_entries, record_with_voucher
from app.tools.reconcile_tools import reconcile_month
from app.tools.time_tools import days_between, get_current_time

# Agent 的工具清单
#
# 关于记账：Agent **不能凭空记账**（没有 record_expense / record_income），
# 唯一能记账的入口是 record_with_voucher —— 它**强制要求凭证文件**，
# 而且登记后状态是「待审核」，要等会计审。
#
# 所以聊天记账不绕过任何流程：
#     出纳页面记账 = 表单 + 凭证
#     聊天记账     = 对话 + 凭证
# 两条路都必须有凭证、都必须过会计审核。
BUILTIN_TOOLS: list[BaseTool] = [
    get_current_time,
    days_between,
    search_accounting_rules,
    # 查询类（只读）
    query_entries,
    get_account_balance,
    query_counterparty,
    reconcile_month,
    find_entries,
    # 记账（必须带凭证，登记为待审核）
    record_with_voucher,
    # 纠错类（只能动待审核的单据）
    delete_last_entry,
    delete_entry_by_id,
]

__all__ = ["BUILTIN_TOOLS"]
