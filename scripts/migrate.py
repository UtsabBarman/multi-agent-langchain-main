#!/usr/bin/env python3
"""Run SQLite migration for app DB (SQLITE_APP_PATH or DATABASE_URL=sqlite://...)."""
from __future__ import annotations

import asyncio
import hashlib
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
        versions_dir = ROOT / "migrations" / "versions"
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await conn.commit()

        cursor = await conn.execute("SELECT filename, checksum FROM schema_migrations")
        applied_rows = await cursor.fetchall()
        await cursor.close()
        applied = {row[0]: row[1] for row in applied_rows}

        for sql_file in sorted(versions_dir.glob("*.sql")):
            sql = sql_file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            prev = applied.get(sql_file.name)
            if prev:
                if prev != checksum:
                    print(f"Migration checksum mismatch: {sql_file.name}")
                    print("Existing migration was modified after being applied. Refusing to continue.")
                    sys.exit(1)
                print(f"Migration {sql_file.name} already applied; skipping.")
                continue

            await conn.executescript(sql)
            await conn.execute(
                "INSERT INTO schema_migrations (filename, checksum) VALUES (?, ?)",
                (sql_file.name, checksum),
            )
            await conn.commit()
            print(f"Migration {sql_file.name} applied successfully.")
    finally:
        await conn.close()


def main():
    asyncio.run(run_migration_sqlite())


if __name__ == "__main__":
    main()
