from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


def create_search_docs_tool(retriever: Any) -> Any:
    """Create a LangChain tool that searches documents via the given retriever."""

    @tool
    def search_docs(query: str, k: int = 5) -> str:
        """Search the document store for relevant passages. Use this to find supporting information."""
        try:
            docs = retriever.invoke(query)
            if not docs:
                return "No relevant documents found."
            parts = []
            for i, d in enumerate(docs[: int(k)], 1):
                content = d.page_content if hasattr(d, "page_content") else str(d)
                parts.append(f"[{i}] {content}")
            return "\n\n".join(parts)
        except Exception as e:
            return f"Search failed: {e}"

    return search_docs
