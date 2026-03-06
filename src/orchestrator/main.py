"""Orchestrator FastAPI app: POST /query -> plan, execute, report."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import uuid
from pathlib import Path

from src.core.config.env import ensure_project_env

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ensure_project_env(_PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("orchestrator")
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.responses import JSONResponse

from src.core.config.loader import load_domain_config
from src.core.contracts.gateway import (
    QueryRequest,
    QueryResponse,
    PlanOnlyResponse,
    ExecuteRequest,
)
from src.core.contracts.orchestrator import Plan, Step, StepResult
from src.data_access.app_db import open_app_db_connection
from src.orchestrator.session import (
    create_request,
    update_request_final,
    save_plan,
    update_plan,
    save_step_result,
    get_request,
    get_plan,
    get_step_results,
    get_latest_request_id,
    get_recent_requests,
    delete_request,
)
from src.orchestrator.planner import build_plan
from src.orchestrator.classifier import classify_query
from src.orchestrator.executor import run_plan, run_step
from src.orchestrator.reporter import synthesize_final_answer
from src.orchestrator.api import doc_db_router
from src.orchestrator.deps import get_app_db

app = FastAPI(title="Multi-Agent: Orchestrator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(doc_db_router, prefix="/api")

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


def _orchestrator_ui_html() -> str:
    """Orchestrator chat UI with agent iframes; labels and icons from domain config."""
    config = get_config()
    agents = config.agents
    # CSS class for avatar color: use name for known agents, else "unknown"
    def _avatar_cls(a) -> str:
        return a.name if a.name in ("researcher", "analyst", "writer") else "unknown"
    iframe_parts = []
    for i, a in enumerate(agents):
        n = i + 1
        label = a.get_display_label()
        letter = a.get_icon_letter()
        cls = _avatar_cls(a)
        iframe_parts.append(
            f'<div class="iframe-wrap" id="agent{n}-wrap">'
            f'<div class="iframe-head">'
            f'<span class="plan-avatar {html.escape(cls)}" title="{html.escape(label)}">{html.escape(letter)}</span>'
            f'<span class="iframe-head-label">{html.escape(label)}</span>'
            f'<button type="button" class="iframe-toggle" title="Minimize" aria-label="Minimize" data-agent-num="{n}">'
            f'<svg class="iframe-toggle-icon iframe-toggle-minimize" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 15l-6-6-6 6"/></svg>'
            f'<svg class="iframe-toggle-icon iframe-toggle-expand" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M6 9l6 6 6-6"/></svg>'
            f'</button></div>'
            f'<div class="iframe-body"><iframe id="agent{n}" title="{html.escape(label)}"></iframe></div></div>'
        )
    iframes_html = "\n      ".join(iframe_parts)
    iframe_src_lines = "\n    ".join(
        f"document.getElementById('agent{i+1}').src = base + ':{a.port}/';"
        for i, a in enumerate(agents)
    )
    agent_meta = {
        a.name.lower(): {
            "label": a.get_display_label(),
            "letter": a.get_icon_letter(),
            "cls": _avatar_cls(a),
            "iframeNum": i + 1,
        }
        for i, a in enumerate(agents)
    }
    agent_meta_js = json.dumps(agent_meta)
    template_path = Path(__file__).parent / "templates" / "orchestrator.html"
    template = template_path.read_text(encoding="utf-8")
    return (
        template.replace("__IFRAMES_HTML__", iframes_html)
        .replace("__IFRAME_SRC_SCRIPT__", iframe_src_lines)
        .replace("__AGENT_META_JS__", agent_meta_js)
    )


@app.get("/", response_class=HTMLResponse)
def orchestrator_ui():
    """Orchestrator chat UI with 3 agent iframes (Option B)."""
    return HTMLResponse(_orchestrator_ui_html())


@app.get("/request/{request_id}")
async def get_request_trace(request_id: str, conn=Depends(get_app_db)):
    """Return full trace for a request: request, plan, step_results. For Chat UI flow and internal chat."""
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")
    req = await get_request(conn, rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    plan = await get_plan(conn, rid)
    step_results = await get_step_results(conn, rid)
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


@app.delete("/request/{request_id}")
async def delete_request_endpoint(request_id: str, conn=Depends(get_app_db)):
    """Permanently delete a chat (request) and its plan/step results from history."""
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")
    req = await get_request(conn, rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    await delete_request(conn, rid)
    return {"ok": True, "request_id": request_id}


@app.get("/trace/last")
async def get_trace_last(domain_id: str | None = None, conn=Depends(get_app_db)):
    """Return full trace for the most recent request (optional domain_id filter). For Chat UI."""
    rid = await get_latest_request_id(conn, domain_id)
    if not rid:
        raise HTTPException(status_code=404, detail="No requests found")
    req = await get_request(conn, rid)
    plan = await get_plan(conn, rid)
    step_results = await get_step_results(conn, rid)
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


@app.get("/history")
async def get_history(limit: int = 50, domain_id: str | None = None, conn=Depends(get_app_db)):
    """Return recent requests for chat history panel (id, query, status, final_answer, created_at)."""
    config = get_config()
    domain_id = domain_id or config.domain_id
    items = await get_recent_requests(conn, limit=min(limit, 100), domain_id=domain_id)
    return {"items": items}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    config = get_config()
    domain_id = req.domain_id or config.domain_id
    env = dict(os.environ)

    log.info("QUERY: %s", (req.query[:200] + "…") if len(req.query) > 200 else req.query)

    try:
        conn = await open_app_db_connection(env)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        request_id = await create_request(conn, domain_id, req.query, req.session_id)
    finally:
        await conn.close()

    try:
        plan = build_plan(req.query, config)
    except Exception as e:
        log.exception("Plan failed")
        await _update_status(env, request_id, "failed", error_message=str(e))
        return QueryResponse(request_id=str(request_id), status="failed", error=str(e))

    for i, s in enumerate(plan.steps, 1):
        log.info("PLAN step %s → %s: %s", i, s.agent_name, (s.task_description[:80] + "…") if len(s.task_description) > 80 else s.task_description)

    conn = await open_app_db_connection(env)
    try:
        await save_plan(conn, request_id, plan)
    finally:
        await conn.close()

    step_results = await run_plan(plan, req.query, config)

    conn = await open_app_db_connection(env)
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
        await _update_status(env, request_id, "partial", error_message=str(e))
        return QueryResponse(request_id=str(request_id), status="partial", final_answer=None, error=str(e))

    log.info("FINAL ANSWER: %s", (final_answer[:300] + "…") if final_answer and len(final_answer) > 300 else (final_answer or "(empty)"))
    await _update_status(env, request_id, "completed", final_answer=final_answer)
    return QueryResponse(request_id=str(request_id), status="completed", final_answer=final_answer)


@app.post("/query/plan", response_model=PlanOnlyResponse)
async def query_plan(req: QueryRequest):
    """Create a request. If the query is a greeting/simple chat, return a short reply; else build plan for user approval."""
    config = get_config()
    domain_id = req.domain_id or config.domain_id
    env = dict(os.environ)
    log.info("QUERY (plan only): %s", (req.query[:200] + "…") if len(req.query) > 200 else req.query)
    try:
        conn = await open_app_db_connection(env)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        request_id = await create_request(conn, domain_id, req.query, req.session_id)
    finally:
        await conn.close()

    try:
        needs_plan, simple_reply = classify_query(req.query)
    except Exception as e:
        log.warning("Classifier failed, defaulting to plan: %s", e)
        needs_plan, simple_reply = True, ""

    if not needs_plan and simple_reply:
        log.info("Simple reply (no plan): %s", (simple_reply[:80] + "…") if len(simple_reply) > 80 else simple_reply)
        conn = await open_app_db_connection(env)
        try:
            await save_plan(conn, request_id, Plan(steps=[]))
        finally:
            await conn.close()
        await _update_status(env, request_id, "completed", final_answer=simple_reply)
        return PlanOnlyResponse(
            request_id=str(request_id),
            status="completed",
            plan={"steps": []},
            final_answer=simple_reply,
        )

    try:
        plan = build_plan(req.query, config)
    except Exception as e:
        log.exception("Plan failed")
        await _update_status(env, request_id, "failed", error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    for i, s in enumerate(plan.steps, 1):
        log.info("PLAN step %s → %s: %s", i, s.agent_name, (s.task_description[:80] + "…") if len(s.task_description) > 80 else s.task_description)
    conn = await open_app_db_connection(env)
    try:
        await save_plan(conn, request_id, plan)
    finally:
        await conn.close()
    await _update_status(env, request_id, "awaiting_approval")
    steps_payload = [s.model_dump() for s in plan.steps]
    return PlanOnlyResponse(request_id=str(request_id), status="awaiting_approval", plan={"steps": steps_payload})


def _validate_plan_steps(plan_payload: list, config) -> Plan:
    """Convert and validate plan payload; raise ValueError if invalid."""
    valid_agents = {a.name for a in config.agents}
    steps = []
    for s in plan_payload or []:
        if not isinstance(s, dict):
            continue
        step_index = s.get("step_index")
        agent_name = (s.get("agent_name") or "").strip()
        task_description = (s.get("task_description") or "").strip()
        if agent_name not in valid_agents:
            raise ValueError(f"Unknown agent: {agent_name}")
        steps.append(Step(step_index=step_index or 0, agent_name=agent_name, task_description=task_description))
    return Plan(steps=steps)


async def _run_execute_only(request_id: uuid.UUID, query: str, plan: Plan, config, env: dict):
    """Run plan execution and reporter only (no planning). Saves step results and final answer."""
    try:
        step_results = await run_plan(plan, query, config)
        conn = await open_app_db_connection(env)
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
        final_answer = synthesize_final_answer(query, step_results)
        log.info("FINAL ANSWER: %s", (final_answer[:300] + "…") if final_answer and len(final_answer) > 300 else (final_answer or "(empty)"))
        await _update_status(env, request_id, "completed", final_answer=final_answer)
    except Exception as e:
        log.exception("Execute failed")
        await _update_status(env, request_id, "failed", error_message=str(e))


@app.post("/query/execute")
async def query_execute(body: ExecuteRequest):
    """Execute the plan for a request (optionally with user-edited plan). Returns 202 + request_id; poll GET /request/{id} for progress."""
    config = get_config()
    env = dict(os.environ)
    try:
        rid = uuid.UUID(body.request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")
    conn = await open_app_db_connection(env)
    try:
        req = await get_request(conn, rid)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        if req["status"] != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail=f"Request not in awaiting_approval status (current: {req['status']}). Submit or cancel only once.",
            )
        plan = await get_plan(conn, rid)
        if not plan or not plan.steps:
            raise HTTPException(status_code=400, detail="No plan found for this request")
        if body.plan is not None and body.plan.steps:
            plan = _validate_plan_steps([s.model_dump() for s in body.plan.steps], config)
            if not plan.steps:
                raise HTTPException(status_code=400, detail="Edited plan must have at least one step")
            await update_plan(conn, rid, plan)
        query_text = req["query"]
    finally:
        await conn.close()
    await _update_status(env, rid, "running")
    asyncio.create_task(_run_execute_only(rid, query_text, plan, config, env))
    return JSONResponse(status_code=202, content={"request_id": body.request_id})


@app.post("/request/{request_id}/cancel")
async def cancel_request(request_id: str, conn=Depends(get_app_db)):
    """Cancel a request that is awaiting_approval. Sets status to cancelled and final_answer to a thanks message."""
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")
    req = await get_request(conn, rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "awaiting_approval":
        raise HTTPException(status_code=409, detail=f"Cannot cancel: request status is {req['status']} (only awaiting_approval can be cancelled)")
    await update_request_final(conn, rid, "cancelled", final_answer="Thanks for using the system.")
    return {"ok": True, "request_id": request_id, "status": "cancelled"}


async def _update_status(env: dict, request_id, status: str, final_answer: str | None = None, error_message: str | None = None):
    conn = await open_app_db_connection(env)
    try:
        await update_request_final(conn, request_id, status, final_answer=final_answer, error_message=error_message)
    finally:
        await conn.close()


async def _run_query_background(request_id: uuid.UUID, query: str, config, env: dict):
    """Run plan step-by-step, saving after each step so the UI can poll and show live progress."""
    try:
        plan = build_plan(query, config)
        for i, s in enumerate(plan.steps, 1):
            log.info("PLAN step %s → %s: %s", i, s.agent_name, (s.task_description[:80] + "…") if len(s.task_description) > 80 else s.task_description)
        conn = await open_app_db_connection(env)
        try:
            await save_plan(conn, request_id, plan)
        finally:
            await conn.close()

        context_parts = [f"Original query: {query}"]
        step_results: list[StepResult] = []
        for step in plan.steps:
            context = "\n".join(context_parts)
            sr = await run_step(step, context, config)
            step_results.append(sr)
            conn = await open_app_db_connection(env)
            try:
                await save_step_result(
                    conn,
                    request_id,
                    sr.step_index,
                    sr.agent_name,
                    {"task": step.task_description},
                    sr.output,
                    sr.status,
                    sr.latency_ms,
                )
            finally:
                await conn.close()
            context_parts.append(f"Step {step.step_index} ({step.agent_name}): {sr.output}")

        final_answer = synthesize_final_answer(query, step_results)
        log.info("FINAL ANSWER: %s", (final_answer[:300] + "…") if final_answer and len(final_answer) > 300 else (final_answer or "(empty)"))
        await _update_status(env, request_id, "completed", final_answer=final_answer)
    except Exception as e:
        log.exception("Background query failed")
        await _update_status(env, request_id, "failed", error_message=str(e))


@app.post("/query/async")
async def query_async(req: QueryRequest):
    """Start query in background; returns request_id immediately. Poll GET /request/{request_id} for live progress."""
    config = get_config()
    domain_id = req.domain_id or config.domain_id
    env = dict(os.environ)
    try:
        conn = await open_app_db_connection(env)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        request_id = await create_request(conn, domain_id, req.query, req.session_id)
    finally:
        await conn.close()

    log.info("QUERY (async): %s", (req.query[:200] + "…") if len(req.query) > 200 else req.query)
    asyncio.create_task(_run_query_background(request_id, req.query, config, env))
    return JSONResponse(status_code=202, content={"request_id": str(request_id)})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
