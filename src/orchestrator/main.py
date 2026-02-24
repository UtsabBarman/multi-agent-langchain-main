"""Orchestrator FastAPI app: POST /query -> plan, execute, report."""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Load .env so POSTGRES_APP_URL etc. are set when orchestrator runs (standalone or via startup.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_PROJECT_ROOT / "config" / "env" / ".env", _PROJECT_ROOT / ".env"):
    if _p.exists():
        load_dotenv(_p, override=False)
        break

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("orchestrator")
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.core.config.loader import load_domain_config
from src.core.contracts.gateway import QueryRequest, QueryResponse
from src.core.contracts.orchestrator import Plan, StepResult
from src.orchestrator.session import (
    get_app_db_url,
    create_request,
    update_request_final,
    save_plan,
    save_step_result,
    get_request,
    get_plan,
    get_step_results,
    get_latest_request_id,
)
from src.orchestrator.planner import build_plan
from src.orchestrator.executor import run_plan
from src.orchestrator.reporter import synthesize_final_answer

app = FastAPI(title="Multi-Agent: Orchestrator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/domains/manufacturing.json")
PROJECT_ROOT = _PROJECT_ROOT
DOMAIN_CONFIG = None


def get_config():
    global DOMAIN_CONFIG
    if DOMAIN_CONFIG is None:
        DOMAIN_CONFIG = load_domain_config(CONFIG_PATH, project_root=PROJECT_ROOT)
    return DOMAIN_CONFIG


@app.on_event("startup")
def startup():
    get_config()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/request/{request_id}")
async def get_request_trace(request_id: str):
    """Return full trace for a request: request, plan, step_results. For Chat UI flow and internal chat."""
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")
    env = dict(os.environ)
    try:
        url = get_app_db_url(env)
    except ValueError:
        url = os.getenv("POSTGRES_APP_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not url:
        raise HTTPException(status_code=500, detail="POSTGRES_APP_URL not set")
    conn = await asyncpg.connect(url)
    try:
        req = await get_request(conn, rid)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        plan = await get_plan(conn, rid)
        step_results = await get_step_results(conn, rid)
    finally:
        await conn.close()
    steps = [s.model_dump() for s in plan.steps] if plan else []
    return {
        "request_id": req["id"],
        "query": req["query"],
        "status": req["status"],
        "final_answer": req["final_answer"],
        "error_message": req["error_message"],
        "created_at": req["created_at"],
        "plan": {"steps": steps},
        "step_results": step_results,
    }


@app.get("/trace/last")
async def get_trace_last(domain_id: str | None = None):
    """Return full trace for the most recent request (optional domain_id filter). For Chat UI."""
    env = dict(os.environ)
    try:
        url = get_app_db_url(env)
    except ValueError:
        url = os.getenv("POSTGRES_APP_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not url:
        raise HTTPException(status_code=500, detail="POSTGRES_APP_URL not set")
    conn = await asyncpg.connect(url)
    try:
        rid = await get_latest_request_id(conn, domain_id)
        if not rid:
            raise HTTPException(status_code=404, detail="No requests found")
        req = await get_request(conn, rid)
        plan = await get_plan(conn, rid)
        step_results = await get_step_results(conn, rid)
    finally:
        await conn.close()
    steps = [s.model_dump() for s in plan.steps] if plan else []
    return {
        "request_id": req["id"],
        "query": req["query"],
        "status": req["status"],
        "final_answer": req["final_answer"],
        "error_message": req["error_message"],
        "created_at": req["created_at"],
        "plan": {"steps": steps},
        "step_results": step_results,
    }


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    config = get_config()
    domain_id = req.domain_id or config.domain_id
    env = dict(os.environ)

    log.info("QUERY: %s", (req.query[:200] + "…") if len(req.query) > 200 else req.query)

    try:
        url = get_app_db_url(env)
    except ValueError:
        url = os.getenv("POSTGRES_APP_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not url:
        raise HTTPException(status_code=500, detail="POSTGRES_APP_URL not set")

    conn = await asyncpg.connect(url)
    try:
        request_id = await create_request(conn, domain_id, req.query, req.session_id)
    finally:
        await conn.close()

    try:
        plan = build_plan(req.query, config)
    except Exception as e:
        log.exception("Plan failed")
        await _update_status(url, request_id, "failed", error_message=str(e))
        return QueryResponse(request_id=str(request_id), status="failed", error=str(e))

    for i, s in enumerate(plan.steps, 1):
        log.info("PLAN step %s → %s: %s", i, s.agent_name, (s.task_description[:80] + "…") if len(s.task_description) > 80 else s.task_description)

    conn = await asyncpg.connect(url)
    try:
        await save_plan(conn, request_id, plan)
    finally:
        await conn.close()

    step_results = await run_plan(plan, req.query, config)

    conn = await asyncpg.connect(url)
    try:
        step_by_idx = {s.step_index: s for s in plan.steps}
        for sr in step_results:
            step = step_by_idx.get(sr.step_index)
            task_desc = step.task_description if step else ""
            await save_step_result(
                conn,
                request_id,
                sr.step_index,
                sr.agent_name,
                {"task": task_desc},
                sr.output,
                sr.status,
                sr.latency_ms,
            )
    finally:
        await conn.close()

    try:
        final_answer = synthesize_final_answer(req.query, step_results)
    except Exception as e:
        log.exception("Synthesis failed")
        await _update_status(url, request_id, "partial", error_message=str(e))
        return QueryResponse(request_id=str(request_id), status="partial", final_answer=None, error=str(e))

    log.info("FINAL ANSWER: %s", (final_answer[:300] + "…") if final_answer and len(final_answer) > 300 else (final_answer or "(empty)"))
    await _update_status(url, request_id, "completed", final_answer=final_answer)
    return QueryResponse(request_id=str(request_id), status="completed", final_answer=final_answer)


async def _update_status(url: str, request_id, status: str, final_answer: str | None = None, error_message: str | None = None):
    conn = await asyncpg.connect(url)
    try:
        await update_request_final(conn, request_id, status, final_answer=final_answer, error_message=error_message)
    finally:
        await conn.close()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
