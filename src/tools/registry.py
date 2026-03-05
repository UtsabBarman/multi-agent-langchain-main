from __future__ import annotations

from typing import Any

from src.tools.rel_db.query import create_query_facts_tool
from src.tools.vector.search import create_search_docs_tool


def get_tools(tool_names: list[str], clients: dict[str, Any]) -> list[Any]:
    """Build a list of LangChain tools from tool_names, injecting clients (SQLite paths + Chroma)."""
    result = []
    for name in tool_names:
        if name == "query_facts":
            # First non-app_db relational client (SQLite path)
            db_path = None
            for k, v in clients.items():
                if k == "app_db":
                    continue
                if isinstance(v, str) and not v.startswith("postgresql"):
                    db_path = v
                    break
            if not db_path:
                continue
            result.append(create_query_facts_tool(db_path))
        elif name == "search_docs":
            retriever = clients.get("docs")
            if retriever is None:
                continue
            result.append(create_search_docs_tool(retriever))
    return result