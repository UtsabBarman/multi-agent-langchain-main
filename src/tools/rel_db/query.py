"""Read-only SQL tool against a SQLite database."""
from __future__ import annotations

import asyncio
import re
from typing import Any

import aiosqlite
from langchain_core.tools import tool

_READ_ONLY_SQL_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _execute_read_only(db_path: str, query: str) -> list[dict[str, Any]]:
    if db_path == ":memory:":
        conn_ctx = aiosqlite.connect(db_path)
    else:
        conn_ctx = aiosqlite.connect(f"file:{db_path}?mode=ro", uri=True)
    async with conn_ctx as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()
        desc = cursor.description
        await cursor.close()
        if not rows or not desc:
            return []
        keys = [c[0] for c in desc]
        return [dict(zip(keys, r)) for r in rows]


def create_query_facts_tool(db_path: str, source_id: str = "manufacturing_db") -> Any:
    """Create a LangChain tool that runs read-only SQL (SELECT only) against the given SQLite path."""

    @tool
    def query_facts(query: str) -> str:
        """Run a read-only SQL query to get facts from the database. Input should be a valid SELECT statement."""
        if not _READ_ONLY_SQL_RE.match(query or ""):
            return "Error: Only read-only SELECT/CTE queries are allowed."
        try:
            rows = _run_async(_execute_read_only(db_path, query))
            if not rows:
                return "No rows returned."
            return str(rows[:50])
        except Exception as e:
            return f"Query failed: {e}"

    return query_facts