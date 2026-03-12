"""Unit tests for tool wrappers: query_facts (SELECT-only), registry."""
import tempfile
from pathlib import Path

from src.tools.registry import _TOOL_FACTORIES, get_tools
from src.tools.rel_db.query import create_query_facts_tool


def test_query_facts_rejects_non_select():
    """query_facts must reject non-SELECT queries."""
    tool = create_query_facts_tool(":memory:")
    out = tool.invoke({"query": "INSERT INTO t VALUES (1)"})
    assert "Only read-only" in out
    out = tool.invoke({"query": "DELETE FROM t"})
    assert "Only read-only" in out


def test_query_facts_accepts_select():
    """query_facts accepts SELECT and returns results (in-memory SQLite)."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        import asyncio

        import aiosqlite
        async def setup():
            async with aiosqlite.connect(path) as conn:
                await conn.execute("CREATE TABLE t(id INT)")
                await conn.execute("INSERT INTO t VALUES (1)")
                await conn.commit()
        asyncio.run(setup())
        tool = create_query_facts_tool(path)
        out = tool.invoke({"query": "SELECT * FROM t"})
        assert "1" in out
    finally:
        Path(path).unlink(missing_ok=True)


def test_registry_known_tool_names():
    """Registry has expected built-in tools."""
    assert "query_facts" in _TOOL_FACTORIES
    assert "search_docs" in _TOOL_FACTORIES
    assert "index_doc" in _TOOL_FACTORIES
    assert "request_user_validation" in _TOOL_FACTORIES


def test_get_tools_returns_empty_for_unknown_names():
    """get_tools with unknown names returns empty list (no crash)."""
    tools = get_tools(["unknown_tool"], {})
    assert tools == []


def test_get_tools_returns_tools_when_clients_provided():
    """get_tools with query_facts and a db path returns one tool."""
    tools = get_tools(["query_facts"], {"manufacturing_db": ":memory:"})
    assert len(tools) == 1
    assert hasattr(tools[0], "invoke")
