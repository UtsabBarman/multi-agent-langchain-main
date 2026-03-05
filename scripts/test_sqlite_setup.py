#!/usr/bin/env python3
"""Verify SQLite app DB and tool wiring work (no OpenAI or full server)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env
from dotenv import load_dotenv
for p in [ROOT / "config" / "env" / ".env", ROOT / ".env"]:
    if p.exists():
        load_dotenv(p)
        break

env = dict(os.environ)


async def test_app_db():
    """Test: open app DB, create request, save plan, fetch request + plan."""
    from src.data_access.app_db import open_app_db_connection
    from src.orchestrator.session import (
        create_request,
        save_plan,
        get_request,
        get_plan,
        get_step_results,
        update_request_final,
    )
    from src.core.contracts.orchestrator import Plan, Step

    if not env.get("SQLITE_APP_PATH") and "sqlite" not in (env.get("DATABASE_URL") or "").lower():
        print("SKIP app_db: SQLITE_APP_PATH or DATABASE_URL not set")
        return True

    conn = await open_app_db_connection(env)
    try:
        request_id = await create_request(conn, "test_domain", "Test query?", None)
        assert request_id is not None
        plan = Plan(steps=[Step(step_index=1, agent_name="researcher", task_description="Look up X")])
        await save_plan(conn, request_id, plan)
        req = await get_request(conn, request_id)
        assert req is not None
        assert req["query"] == "Test query?"
        assert req["status"] == "running"
        plan_loaded = await get_plan(conn, request_id)
        assert plan_loaded is not None
        assert len(plan_loaded.steps) == 1
        assert plan_loaded.steps[0].agent_name == "researcher"
        await update_request_final(conn, request_id, "completed", final_answer="Done.")
        print("  app_db: create_request, save_plan, get_request, get_plan, update_request_final OK")
        return True
    finally:
        await conn.close()


def test_factory_and_tools():
    """Test: build_clients returns SQLite paths and query_facts tool is created."""
    from src.core.config.loader import load_domain_config
    from src.data_access.factory import build_clients
    from src.tools.registry import get_tools

    config = load_domain_config("config/domains/manufacturing.json", project_root=ROOT)
    clients = build_clients(config, project_root=ROOT)
    assert "app_db" in clients or "manufacturing_db" in clients, "Expected at least one rel_db client"
    # manufacturing_db should be a path (string, not postgres URL)
    for k, v in clients.items():
        if k != "docs" and isinstance(v, str):
            assert not v.startswith("postgresql"), f"Expected SQLite path, got postgres URL in clients[{k!r}]"
    # Researcher has query_facts; tool should be registered when manufacturing_db path is present
    tools = get_tools(["query_facts", "search_docs"], clients)
    query_facts_tools = [t for t in tools if getattr(t, "name", "") == "query_facts"]
    if env.get("SQLITE_MANUFACTURING_PATH") or "manufacturing_db" in clients:
        assert len(query_facts_tools) >= 1, "query_facts tool should be built when SQLite path available"
    print("  factory + registry: clients and query_facts tool OK")
    return True


async def main():
    print("Testing SQLite setup...")
    ok = True
    try:
        await test_app_db()
    except Exception as e:
        print(f"  app_db FAIL: {e}")
        ok = False
    try:
        test_factory_and_tools()
    except Exception as e:
        print(f"  factory/tools FAIL: {e}")
        ok = False
    if ok:
        print("All checks passed.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
