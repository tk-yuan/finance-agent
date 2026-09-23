"""聊天模型工厂：统一从这里拿模型。

好处：业务代码不直接 new 模型，换服务商（硅基流动→DeepSeek）只改这里。
"""

from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import Settings, get_settings


def build_chat_model(settings: Settings | None = None, *, temperature: float = 0.0) -> BaseChatModel:
    """按配置构建对话模型。

    `openai:` 前缀的意思是：走 OpenAI 兼容协议访问硅基流动
    （硅基流动的接口格式和 OpenAI 一样，所以能用同一套调用方式）。

    `enable_thinking=False`：Qwen3 系列默认开启「思考模式」，会先生成一大段
    推理过程再回答，单次调用可能超过 2 分钟。记账/查账这类任务不需要长推理，
    关掉它能把响应时间降到几秒。
    """
    settings = settings or get_settings()
    return init_chat_model(
        f"openai:{settings.siliconflow_chat_model}",
        base_url=settings.siliconflow_base_url,
        api_key=settings.siliconflow_api_key,
        temperature=temperature,
        extra_body={"enable_thinking": False},
    )


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """进程内复用的模型实例（模型对象无状态，可安全共享）。"""
    return build_chat_model()
