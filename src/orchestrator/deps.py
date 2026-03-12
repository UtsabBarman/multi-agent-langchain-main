"""Orchestrator dependencies (config, app DB connection)."""
from __future__ import annotations

from typing import AsyncGenerator

from fastapi import HTTPException

from src.data_access.app_db import open_app_db_connection


async def get_app_db() -> AsyncGenerator:
    """Yield an app DB connection; closes on exit. Raise 500 if env not set."""
    import os
    env = dict(os.environ)
    try:
        conn = await open_app_db_connection(env)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        yield conn
    finally:
        await conn.close()
