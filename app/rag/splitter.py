"""文本切分：把长文档切成适合检索的块（中文友好分隔符）。"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings

_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]


def split_documents(documents: list) -> list:
    s = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        separators=_SEPARATORS,
        chunk_size=s.chunk_size,
        chunk_overlap=s.chunk_overlap,
    )
    return splitter.split_documents(documents)
