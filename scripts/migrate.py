#!/usr/bin/env python3
"""Run migrations against POSTGRES_APP_URL."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

# Load env
for p in [ROOT / "config" / "env" / ".env", ROOT / ".env"]:
    if p.exists():
        load_dotenv(p)
        break

POSTGRES_APP_URL = os.getenv("POSTGRES_APP_URL")
if not POSTGRES_APP_URL:
    print("POSTGRES_APP_URL not set. Set it in config/env/.env or .env")
    sys.exit(1)

# asyncpg URL -> psycopg2-style for running raw SQL (sync)
# We run SQL with asyncpg in sync style via asyncio.run, or use a sync driver.
# Simplest: use asyncpg with asyncio to run the migration file.
import asyncio
import asyncpg


async def run_migration():
    # asyncpg uses postgresql:// not postgresql+asyncpg://
    url = POSTGRES_APP_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        sql_path = ROOT / "migrations" / "versions" / "001_initial.sql"
        sql = sql_path.read_text(encoding="utf-8")
        # Remove single-line comments and split by semicolon
        lines = [line for line in sql.split("\n") if not line.strip().startswith("--")]
        clean = "\n".join(lines)
        for stmt in clean.split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(stmt + ";")
        print("Migration 001_initial.sql applied successfully.")
    finally:
        await conn.close()


def main():
    asyncio.run(run_migration())


if __name__ == "__main__":
    main()
