"""Tool to index document text into Chroma so it becomes searchable via search_docs."""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.data_access.vector.indexing import index_text_to_chroma


def create_index_doc_tool(chroma_path: str, collection_name: str = "default") -> Any:
    """Create a LangChain tool that indexes text into Chroma (chunk, embed, add to collection)."""

    @tool
    def index_doc(content: str, source: str = "researcher") -> str:
        """Index document content into the vector store so it can be found by search_docs.
        Use this when you have new information or a document to add to the knowledge base.
        Input: the full text content to index. Optionally set source to label where it came from."""
        if not (content or "").strip():
            return "Error: content cannot be empty."
        try:
            n = index_text_to_chroma(chroma_path, collection_name, content, source=source)
            if n == 0:
                return "No chunks produced from content."
            return f"Indexed {n} chunks into collection '{collection_name}' (source: {source})."
        except Exception as e:
            return f"Indexing failed: {e}"

    return index_doc
