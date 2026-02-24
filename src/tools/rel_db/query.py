from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
from langchain_core.tools import tool


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _execute_read_only(pg_url: str, query: str) -> list[dict[str, Any]]:
    url = pg_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def create_query_facts_tool(pg_url: str, source_id: str = "manufacturing_db") -> Any:
    """Create a LangChain tool that runs read-only SQL against the given Postgres URL."""

    @tool
    def query_facts(query: str) -> str:
        """Run a read-only SQL query to get facts from the database. Input should be a valid SELECT statement."""
        if not query.strip().upper().startswith("SELECT"):
            return "Error: Only SELECT queries are allowed."
        try:
            rows = _run_async(_execute_read_only(pg_url, query))
            if not rows:
                return "No rows returned."
            return str(rows[:50])  # Limit to 50 rows for context
        except Exception as e:
            return f"Query failed: {e}"

    return query_facts
