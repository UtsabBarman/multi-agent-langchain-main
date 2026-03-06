"""Persist and load request state (requests, plans, step_results) in app DB."""
from __future__ import annotations

import json
import uuid
from typing import Any

from src.core.contracts.orchestrator import Plan, StepResult
from src.data_access.app_db.base import AppDbConnectionBase as AppDbConnection


async def create_request(
    conn: AppDbConnection,
    domain_id: str,
    query: str,
    session_id: str | uuid.UUID | None = None,
) -> uuid.UUID:
    del session_id  # unused in minimal schema
    request_id = uuid.uuid4()
    await conn.execute(
        f"""
        INSERT INTO {conn.requests_table} (id, domain_id, query, status)
        VALUES ($1, $2, $3, 'running')
        """,
        request_id,
        domain_id,
        query,
    )
    return request_id


async def update_request_final(
    conn: AppDbConnection,
    request_id: uuid.UUID,
    status: str,
    final_answer: str | None = None,
    error_message: str | None = None,
) -> None:
    await conn.execute(
        f"""
        UPDATE {conn.requests_table} SET status = $1, final_answer = $2, error_message = $3, updated_at = now()
        WHERE id = $4
        """,
        status,
        final_answer,
        error_message,
        request_id,
    )


async def save_plan(conn: AppDbConnection, request_id: uuid.UUID, plan: Plan) -> None:
    steps_json = json.dumps([s.model_dump() for s in plan.steps])
    await conn.execute(
        f"INSERT INTO {conn.plans_table} (request_id, steps) VALUES ($1, $2::jsonb)",
        request_id,
        steps_json,
    )


async def update_plan(conn: AppDbConnection, request_id: uuid.UUID, plan: Plan) -> None:
    """Update the stored plan for a request (e.g. after user edits)."""
    steps_json = json.dumps([s.model_dump() for s in plan.steps])
    await conn.execute(
        f"UPDATE {conn.plans_table} SET steps = $1::jsonb WHERE request_id = $2",
        steps_json,
        request_id,
    )


async def save_step_result(
    conn: AppDbConnection,
    request_id: uuid.UUID,
    step_index: int,
    agent_name: str,
    input_payload: dict,
    output_payload: dict | str,
    status: str,
    latency_ms: int | None,
) -> None:
    in_json = json.dumps(input_payload)
    out_json = json.dumps(output_payload) if isinstance(output_payload, dict) else json.dumps({"text": output_payload})
    await conn.execute(
        f"""
        INSERT INTO {conn.step_results_table} (request_id, step_index, agent_name, input_payload, output_payload, status, latency_ms)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7)
        """,
        request_id,
        step_index,
        agent_name,
        in_json,
        out_json,
        status,
        latency_ms,
    )


async def get_plan(conn: AppDbConnection, request_id: uuid.UUID) -> Plan | None:
    from src.core.contracts.orchestrator import Step
    row = await conn.fetchrow(f"SELECT steps FROM {conn.plans_table} WHERE request_id = $1", request_id)
    if not row:
        return None
    steps_raw = row["steps"]
    if isinstance(steps_raw, str):
        steps_raw = json.loads(steps_raw)
    if not isinstance(steps_raw, list):
        steps_raw = []
    return Plan(steps=[Step(**s) for s in steps_raw if isinstance(s, dict)])


async def get_request(
    conn: AppDbConnection,
    request_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Load one request by id. Returns dict with id, domain_id, query, status, final_answer, error_message, created_at."""
    row = await conn.fetchrow(
        f"""
        SELECT id, domain_id, query, status, final_answer, error_message, created_at
        FROM {conn.requests_table} WHERE id = $1
        """,
        request_id,
    )
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "domain_id": row["domain_id"],
        "query": row["query"],
        "status": row["status"],
        "final_answer": row["final_answer"],
        "error_message": row["error_message"],
        "created_at": (row["created_at"].isoformat() if hasattr(row.get("created_at"), "isoformat") else str(row["created_at"])) if row.get("created_at") else None,
    }


async def get_step_results(
    conn: AppDbConnection,
    request_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Load step_results for a request, ordered by step_index."""
    rows = await conn.fetch(
        f"""
        SELECT step_index, agent_name, input_payload, output_payload, status, latency_ms
        FROM {conn.step_results_table} WHERE request_id = $1 ORDER BY step_index
        """,
        request_id,
    )
    return [
        {
            "step_index": r["step_index"],
            "agent_name": r["agent_name"],
            "input_payload": r["input_payload"],
            "output_payload": r["output_payload"],
            "status": r["status"],
            "latency_ms": r["latency_ms"],
        }
        for r in rows
    ]


async def get_latest_request_id(
    conn: AppDbConnection,
    domain_id: str | None = None,
) -> uuid.UUID | None:
    """Return the most recent request id, optionally filtered by domain_id."""
    if domain_id:
        row = await conn.fetchrow(
            f"SELECT id FROM {conn.requests_table} WHERE domain_id = $1 ORDER BY created_at DESC LIMIT 1",
            domain_id,
        )
    else:
        row = await conn.fetchrow(
            f"SELECT id FROM {conn.requests_table} ORDER BY created_at DESC LIMIT 1",
        )
    return row["id"] if row else None


async def delete_request(conn: AppDbConnection, request_id: uuid.UUID) -> bool:
    """Permanently delete a request and its plan and step_results. Returns True if a row was deleted."""
    await conn.execute(
        f"DELETE FROM {conn.step_results_table} WHERE request_id = $1",
        request_id,
    )
    await conn.execute(
        f"DELETE FROM {conn.plans_table} WHERE request_id = $1",
        request_id,
    )
    await conn.execute(
        f"DELETE FROM {conn.requests_table} WHERE id = $1",
        request_id,
    )
    return True


async def get_recent_requests(
    conn: AppDbConnection,
    limit: int = 50,
    domain_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent requests for chat history: id, query, status, final_answer, created_at."""
    if domain_id:
        rows = await conn.fetch(
            f"""
            SELECT id, query, status, final_answer, created_at
            FROM {conn.requests_table} WHERE domain_id = $1 ORDER BY created_at DESC LIMIT $2
            """,
            domain_id,
            limit,
        )
    else:
        rows = await conn.fetch(
            f"""
            SELECT id, query, status, final_answer, created_at
            FROM {conn.requests_table} ORDER BY created_at DESC LIMIT $1
            """,
            limit,
        )
    return [
        {
            "id": str(r["id"]),
            "query": r["query"] or "",
            "status": r["status"] or "",
            "final_answer": (r["final_answer"] or "")[:500],
            "created_at": (r["created_at"].isoformat() if hasattr(r.get("created_at"), "isoformat") else str(r["created_at"])) if r.get("created_at") else None,
        }
        for r in rows
    ]
