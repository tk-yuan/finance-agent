"""RAG 门面：对外提供 ingest / retrieve 两个入口。"""

from __future__ import annotations

from app.rag.loaders import load_text
from app.rag.splitter import split_documents
from app.rag.vectorstore import add_documents, similarity_search


def ingest_text(file_path: str) -> int:
    """把一份文本灌进知识库，返回块数。"""
    docs = load_text(file_path)
    chunks = split_documents(docs)
    add_documents(chunks)
    return len(chunks)


def retrieve(query: str, k: int = 4) -> str:
    """检索相关片段，拼成带来源的文本。"""
    docs = similarity_search(query, k=k)
    if not docs:
        return ""
    lines = [f"[{d.metadata.get('source', '?')}]\n{d.page_content}" for d in docs]
    return "\n\n".join(lines)
