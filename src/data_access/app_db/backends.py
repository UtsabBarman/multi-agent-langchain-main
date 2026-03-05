"""App DB: SQLite only (aiosqlite)."""
from __future__ import annotations

from src.data_access.app_db.base import AppDbConnectionBase
from src.data_access.app_db.sqlite_conn import open_sqlite_connection


async def open_app_db_connection(env: dict[str, str]) -> AppDbConnectionBase:
    """Open the app SQLite connection. Requires SQLITE_APP_PATH or DATABASE_URL=sqlite://..."""
    return await open_sqlite_connection(env)


def get_app_db_url(env: dict[str, str]) -> str:
    """Return path/URL for app DB (e.g. for migrate script)."""
    path = (
        env.get("SQLITE_APP_PATH")
        or (env.get("DATABASE_URL", "").replace("sqlite:///", "").replace("sqlite://", "").strip())
    )
    if not path:
        raise ValueError("SQLITE_APP_PATH or DATABASE_URL (sqlite://...) must be set")
    return path
