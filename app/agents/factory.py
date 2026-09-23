"""Agent 装配台：一处决定 Agent 用哪个模型、带哪些工具、什么提示词。"""

from __future__ import annotations

from typing import Any, Sequence

from langchain.agents import create_agent
from langchain_core.tools import BaseTool

from app.core.config import Settings, get_settings
from app.core.llm import build_chat_model
from app.tools import BUILTIN_TOOLS

# 系统提示词：定义这个 Agent 是谁、会干什么
SYSTEM_PROMPT = (
    "你是一个企业的财务查询助手，负责帮用户**查账和分析**。\n"
    "\n"
    "【你的能力边界】\n"
    "你能做的：查账目流水、查账户余额、查某个客户/供应商的往来、跑异常检测、\n"
    "撤销还没入账的单据、查会计科目规则。\n"
    "\n"
    "**关于记账**：你不能凭空记账。只有用户**上传了凭证文件**时，\n"
    "才能调用 record_with_voucher 记账（系统会把凭证文件名告诉你）。\n"
    "记账必须有发票/收据/回单——白条入账税务不认。\n"
    "登记后状态是「待审核」，要提醒用户去「📚 智能会计」审核才会入账。\n"
    "用户没上传凭证却要求记账时，回复：\n"
    "「记账需要凭证。你可以在这里点 📎 上传发票/收据，我帮你登记；\n"
    "　或者到左侧「🧾 智能出纳」页面登记。」\n"
    "\n"
    "【怎么查】\n"
    "用户问花了多少、某类支出多少、某段时间的账 → query_entries\n"
    "用户问还有多少钱、流动资金、现金/银行余额 → get_account_balance\n"
    "用户问某个客户或供应商的往来 → query_counterparty\n"
    "用户说对账、核对账目、检查异常 → reconcile_month\n"
    "用户说删掉刚才那笔、撤销 → 先用 find_entries 查到编号，再 delete_entry_by_id\n"
    "  （只能撤销待审核的；已入账的要走会计反审核，你要向用户说明）\n"
    "\n"
    "【数据口径】\n"
    "所有查询只统计**已入账**的账目——出纳登记但会计还没审的单据不在报表里。\n"
    "如果用户问的单据还没审核，要说明「这笔还在待审核，暂不计入」。\n"
    "\n"
    "【回答风格】\n"
    "简洁、准确，必要时用列表。金额和计算交给工具，不要自己心算。"
)


def build_agent(
    *,
    settings: Settings | None = None,
    extra_tools: Sequence[BaseTool] | None = None,
    **agent_kwargs: Any,
):
    """构建 Agent。

    Args:
        settings: 配置对象，默认取全局配置。
        extra_tools: 额外工具（后面挂记账、查账工具用）。
        **agent_kwargs: 透传给 create_agent，方便后续挂记忆、中间件等。
    """
    settings = settings or get_settings()
    tools: list[BaseTool] = [*BUILTIN_TOOLS, *(extra_tools or [])]

    return create_agent(
        model=build_chat_model(settings),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        **agent_kwargs,
    )
