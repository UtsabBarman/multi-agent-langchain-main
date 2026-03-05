"""SQLite app DB connection (aiosqlite) with unified interface."""
from __future__ import annotations

import re
import uuid
from typing import Any

import aiosqlite

from src.data_access.app_db.base import AppDbConnectionBase


def _pg_to_sqlite_params(params: tuple[Any, ...]) -> tuple[Any, ...]:
    """Convert params for SQLite (e.g. UUID -> str)."""
    out = []
    for p in params:
        if isinstance(p, uuid.UUID):
            out.append(str(p))
        else:
            out.append(p)
    return tuple(out)


def _pg_to_sqlite_sql(sql: str) -> str:
    """Convert Postgres-style $1,$2, ::jsonb, and now() to SQLite-friendly form."""
    out = sql
    out = re.sub(r"::jsonb", "", out)
    out = re.sub(r"\$\d+", "?", out)
    out = re.sub(r"\bnow\(\)", "datetime('now')", out)
    return out


async def open_sqlite_connection(env: dict[str, str]) -> AppDbConnectionBase:
    path = (
        env.get("SQLITE_APP_PATH")
        or env.get("DATABASE_URL", "").replace("sqlite:///", "").replace("sqlite://", "").strip()
    )
    if not path:
        raise ValueError("SQLITE_APP_PATH or DATABASE_URL (sqlite://...) not set")
    raw = await aiosqlite.connect(path)
    raw.row_factory = aiosqlite.Row
    return _SQLiteConnection(raw)


class _SQLiteConnection(AppDbConnectionBase):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self.requests_table = "app_requests"
        self.plans_table = "app_plans"
        self.step_results_table = "app_step_results"

    async def execute(self, sql: str, *params: Any) -> None:
        sql = _pg_to_sqlite_sql(sql)
        await self._conn.execute(sql, _pg_to_sqlite_params(params))
        await self._conn.commit()

    async def fetchrow(self, sql: str, *params: Any) -> dict[str, Any] | None:
        sql = _pg_to_sqlite_sql(sql)
        cursor = await self._conn.execute(sql, _pg_to_sqlite_params(params))
        row = await cursor.fetchone()
        desc = cursor.description
        await cursor.close()
        if row is None:
            return None
        return dict(zip([c[0] for c in desc], row)) if desc else None

    async def fetch(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        sql = _pg_to_sqlite_sql(sql)
        cursor = await self._conn.execute(sql, _pg_to_sqlite_params(params))
        rows = await cursor.fetchall()
        desc = cursor.description
        await cursor.close()
        if not rows or not desc:
            return []
        keys = [c[0] for c in desc]
        return [dict(zip(keys, r)) for r in rows]

    async def close(self) -> None:
        await self._conn.close()
