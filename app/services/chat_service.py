"""业务服务层：与 Web 框架无关。

FastAPI 调用它；以后若要加命令行、或换 Flask，复用同一套逻辑。
"""

from __future__ import annotations

from app.agents.factory import build_agent
from app.core.exceptions import AppError
from app.schemas.chat import ChatRequest, ChatResponse, ToolCall
from app.services import conversation_service

# 工具名 → (友好标签, 动作类型)
# 前端靠这个把「记账」和「查询」区分开，用户一眼能看出 Agent 干了什么
TOOL_LABELS: dict[str, tuple[str, str]] = {
    "record_expense": ("记账", "record"),
    "record_income": ("记账", "record"),
    "record_asset_purchase": ("记资产", "record"),
    "record_with_voucher": ("凭证记账", "record"),
    "query_entries": ("查询", "query"),
    "get_account_balance": ("查余额", "query"),
    "query_counterparty": ("查往来", "query"),
    "reconcile_month": ("对账", "reconcile"),
    "search_accounting_rules": ("查科目规则", "query"),
    "get_current_time": ("查时间", "query"),
    "days_between": ("算天数", "query"),
    "delete_last_entry": ("撤销记账", "delete"),
    "delete_entry_by_id": ("删除账目", "delete"),
    "find_entries": ("查找账目", "query"),
}


class ChatService:
    """对话编排：把一次用户请求变成一次 Agent 调用。

    关键：每次调用都会带上该会话最近几条历史消息，
    否则 Agent 是无状态的——它不记得用户上一句说了什么。
    """

    def __init__(self, agent=None) -> None:
        self._agent = agent

    @property
    def agent(self):
        if self._agent is None:
            self._agent = build_agent()
        return self._agent

    def chat(self, request: ChatRequest | None = None, *,
             message: str = "", session_id: str = "default",
             voucher_name: str = "") -> ChatResponse:
        """处理一次对话。

        voucher_name 非空表示用户这次上传了凭证——会告诉 Agent，
        Agent 才能在调用 record_with_voucher 时填对文件名。
        """
        conv_id = session_id or (request.session_id if request else "default")
        user_message = message or (request.message if request else "")

        # 1. 确保会话存在，并取出历史上下文
        conversation_service.ensure_conversation(conv_id)
        history = conversation_service.load_history(conv_id)

        # 2. 存下用户这条消息（第一条消息顺便作为会话标题）
        conversation_service.add_message(conv_id, "user", user_message, auto_title=True)

        # 3. 有凭证就把文件名告诉 Agent（否则它没有权限记账）
        content = user_message
        if voucher_name:
            content = (
                f"{user_message}\n\n"
                f"〔系统信息：用户本次上传了凭证，文件名为 {voucher_name}。"
                f"如果用户要求记账，调用 record_with_voucher 时 voucher 参数填这个文件名。〕"
            )

        messages = [*history, {"role": "user", "content": content}]
        try:
            result = self.agent.invoke({"messages": messages})
        except Exception as exc:
            raise AppError(f"模型调用失败：{exc}") from exc

        answer = _extract_answer(result)
        tool_calls = _extract_tool_calls(result)

        # 4. 存下回答
        conversation_service.add_message(conv_id, "assistant", answer)

        # 5. 判断这次是「记账」还是「查询」，前端据此显示不同颜色
        kinds = [TOOL_LABELS.get(tc.name, ("", "chat"))[1] for tc in tool_calls]
        if "record" in kinds:
            kind = "record"
        elif "reconcile" in kinds:
            kind = "reconcile"
        elif "query" in kinds:
            kind = "query"
        else:
            kind = "chat"

        return ChatResponse(
            session_id=conv_id, answer=answer, tool_calls=tool_calls, kind=kind
        )


def _extract_tool_calls(result) -> list[ToolCall]:
    """收集本次调用触发了哪些工具，转成前端能显示的标签。"""
    calls: list[ToolCall] = []
    messages = result.get("messages", []) if isinstance(result, dict) else []
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name", "unknown")
            label, _ = TOOL_LABELS.get(name, (name, "chat"))
            args = call.get("args") or {}
            # 挑一个最能说明问题的参数做摘要
            summary = args.get("description") or args.get("query") or args.get("item") or ""
            amount = args.get("amount")
            if amount:
                summary = f"{summary} {amount:,.2f}元".strip()
            calls.append(ToolCall(name=name, label=label, arg=str(summary)[:60]))
    return calls


def _extract_answer(result) -> str:
    """从 Agent 返回值里取出最后一条 AI 的文本回答。"""
    messages = result.get("messages", []) if isinstance(result, dict) else []
    for msg in reversed(messages):
        if getattr(msg, "type", "") != "ai":
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text = "".join(p.get("text", "") for p in content if isinstance(p, dict)).strip()
            if text:
                return text
    return ""
