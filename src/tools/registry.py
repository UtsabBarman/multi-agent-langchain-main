from __future__ import annotations

from typing import Any

from src.tools.rel_db.query import create_query_facts_tool
from src.tools.vector.search import create_search_docs_tool


def get_tools(tool_names: list[str], clients: dict[str, Any]) -> list[Any]:
    """Build a list of LangChain tools from tool_names, injecting clients."""
    result = []
    for name in tool_names:
        if name == "query_facts":
            # Use first available Postgres client (skip app_db if we want only connected DBs for tools)
            pg_url = None
            for k, v in clients.items():
                if k == "app_db":
                    continue
                if isinstance(v, str) and v.startswith("postgresql"):
                    pg_url = v
                    break
            if not pg_url:
                continue
            result.append(create_query_facts_tool(pg_url))
        elif name == "search_docs":
            retriever = clients.get("docs")
            if retriever is None:
                continue
            result.append(create_search_docs_tool(retriever))
    return result
