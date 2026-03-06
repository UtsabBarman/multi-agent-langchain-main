from __future__ import annotations

from typing import Any, Callable

from src.tools.rel_db.query import create_query_facts_tool
from src.tools.vector.search import create_search_docs_tool
from src.tools.vector.index_doc import create_index_doc_tool


def _query_facts_factory(clients: dict[str, Any]) -> Any | None:
    db_path = next(
        (v for k, v in clients.items() if k != "app_db" and isinstance(v, str) and not v.startswith("postgresql")),
        None,
    )
    return create_query_facts_tool(db_path) if db_path else None


def _search_docs_factory(clients: dict[str, Any]) -> Any | None:
    retriever = clients.get("docs")
    return create_search_docs_tool(retriever) if retriever else None


def _index_doc_factory(clients: dict[str, Any]) -> Any | None:
    cfg = clients.get("docs_index")
    if not isinstance(cfg, dict):
        return None
    path = cfg.get("path")
    if not path:
        return None
    return create_index_doc_tool(path, cfg.get("collection_name", "default"))


_TOOL_FACTORIES: dict[str, Callable[[dict[str, Any]], Any | None]] = {
    "query_facts": _query_facts_factory,
    "search_docs": _search_docs_factory,
    "index_doc": _index_doc_factory,
}


def get_tools(tool_names: list[str], clients: dict[str, Any]) -> list[Any]:
    """Build a list of LangChain tools from tool_names, injecting clients (SQLite paths + Chroma)."""
    result = []
    for name in tool_names:
        factory = _TOOL_FACTORIES.get(name)
        if not factory:
            continue
        tool = factory(clients)
        if tool is not None:
            result.append(tool)
    return result