"""文档加载：把企业的财务制度文档读成文本。"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import TextLoader

from app.core.exceptions import AppError


def load_text(file_path: str | Path) -> list:
    """加载一个文本/markdown 文件，返回 LangChain Document 列表。"""
    path = Path(file_path)
    if not path.exists():
        raise AppError(f"文件不存在：{path}")
    docs = TextLoader(str(path), encoding="utf-8").load()
    for d in docs:
        d.metadata.setdefault("source", path.name)
    return [d for d in docs if d.page_content.strip()]
