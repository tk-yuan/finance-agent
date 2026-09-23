"""向量化模型工厂（RAG 用）。"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings, get_settings


def build_embeddings(settings: Settings | None = None) -> OpenAIEmbeddings:
    settings = settings or get_settings()
    return OpenAIEmbeddings(
        model=settings.siliconflow_embed_model,
        base_url=settings.siliconflow_base_url,
        api_key=settings.siliconflow_api_key,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    return build_embeddings()
