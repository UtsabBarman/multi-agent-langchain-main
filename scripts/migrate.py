#!/usr/bin/env python3
"""Run SQLite migration for app DB (SQLITE_APP_PATH or DATABASE_URL=sqlite://...)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config.env import ensure_project_env

ensure_project_env(ROOT)
env = dict(os.environ)


async def run_migration_sqlite():
    import aiosqlite
    path = (
        env.get("SQLITE_APP_PATH")
        or env.get("DATABASE_URL", "").replace("sqlite:///", "").replace("sqlite://", "").strip()
    )
    if not path:
        print("SQLITE_APP_PATH or DATABASE_URL (sqlite://...) not set. Set it in config/env/.env or .env")
        sys.exit(1)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path)
    try:
        sql_path = ROOT / "migrations" / "versions" / "001_initial_sqlite.sql"
        sql = sql_path.read_text(encoding="utf-8")
        lines = [line for line in sql.split("\n") if not line.strip().startswith("--")]
        clean = "\n".join(lines)
        for stmt in clean.split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(stmt + ";")
        await conn.commit()
        print("Migration 001_initial_sqlite.sql applied successfully.")
    finally:
        await conn.close()


def main():
    asyncio.run(run_migration_sqlite())


if __name__ == "__main__":
    main()
