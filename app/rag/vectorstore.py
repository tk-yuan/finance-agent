"""向量库：Chroma（本地、免 Docker），持久化到磁盘。"""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import get_settings
from app.core.embeddings import get_embeddings

_store = None


def get_vector_store() -> Chroma:
    global _store
    if _store is None:
        s = get_settings()
        Path(s.chroma_dir).mkdir(parents=True, exist_ok=True)
        _store = Chroma(
            collection_name="finance_kb",
            embedding_function=get_embeddings(),
            persist_directory=s.chroma_dir,
        )
    return _store


def add_documents(documents: list[Document]) -> None:
    if documents:
        get_vector_store().add_documents(documents)


def similarity_search(query: str, k: int = 4) -> list[Document]:
    return get_vector_store().similarity_search(query, k=k)
