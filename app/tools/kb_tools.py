"""知识库工具：让 Agent 能检索企业私有的财务制度/科目字典。

这体现了「企业私有财务库」的价值：科目分类规则不是写死在代码里，
而是存在企业自己的知识库里，Agent 分类前先检索它。
"""

from __future__ import annotations

from langchain.tools import tool

from app.rag.pipeline import retrieve


@tool
def search_accounting_rules(query: str) -> str:
    """检索企业财务制度/科目字典，获取费用分类规则。

    当你不确定一笔支出该归哪个科目时，先调用本工具查规则。
    返回企业私有知识库中相关的科目说明和记账规则。

    Args:
        query: 要查的支出场景，如"打车算什么科目""买办公用品算什么科目"。
    """
    text = retrieve(query, k=3)
    if not text:
        return "知识库中没有相关规则。请按常识选最贴近的费用科目。"
    return text
