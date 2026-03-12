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
from src.core.logging_config import configure_log_format

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ensure_project_env(_PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
configure_log_format()
log = logging.getLogger("orchestrator")
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.responses import JSONResponse

from src.core.config.loader import load_domain_config
from src.core.contracts.gateway import (
    ExecuteRequest,
    PlanOnlyResponse,
    QueryRequest,
    QueryResponse,
    RespondRequest,
)
from src.core.contracts.orchestrator import Plan, Step, StepResult
from src.data_access.app_db import open_app_db_connection
from src.orchestrator.api import doc_db_router
from src.orchestrator.classifier import classify_query
from src.orchestrator.deps import get_app_db
from src.orchestrator.executor import run_plan, run_step
from src.orchestrator.plan_validation import topological_order, validate_and_normalize_plan
from src.orchestrator.planner import build_plan
from src.orchestrator.reporter import synthesize_final_answer
from src.orchestrator.session import (
    append_run_event,
    create_request,
    delete_request,
    get_latest_request_id,
    get_plan,
    get_recent_requests,
    get_request,
    get_run_events,
    get_step_results,
    save_plan,
    save_step_result,
    update_plan,
    update_request_clear_paused,
    update_request_final,
    update_request_paused,
    update_step_result,
)

app = FastAPI(title="Multi-Agent: Orchestrator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def optional_api_key_middleware(request, call_next):
    """If ORCHESTRATOR_API_KEY is set, require X-API-Key header to match. Skip /health."""
    api_key = os.environ.get("ORCHESTRATOR_API_KEY", "").strip()
    if api_key and request.url.path != "/health":
        key = request.headers.get("X-API-Key", "")
        if key != api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing X-API-Key"})
    return await call_next(request)


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


@app.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str, since_ts: str | None = None):
    """Stream run events as Server-Sent Events. Run migration 003 first. Use since_ts for incremental (e.g. after last event ts)."""
    try:
        uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    env = dict(os.environ)
    conn = await open_app_db_connection(env)
    try:
        events = await get_run_events(conn, run_id, since_ts=since_ts)
    finally:
        await conn.close()

    async def generate():
        for ev in events:
            line = f"data: {json.dumps({'ts': ev.get('ts'), 'event_type': ev.get('event_type'), 'payload': ev.get('payload')})}\n\n"
            yield line

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


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
    out = {
        "request_id": req["id"],
        "query": req["query"],
        "status": req["status"],
        "final_answer": req["final_answer"],
        "error_message": req["error_message"],
        "created_at": req["created_at"],
        "plan": {"steps": steps},
        "step_results": step_results,
    }
    if req.get("status") == "awaiting_user_input":
        out["paused_at_step"] = req.get("paused_at_step")
        out["validation"] = req.get("validation_payload")
    return out


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
        plan = validate_and_normalize_plan(plan, config)
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

    step_results = await run_plan(plan, req.query, config, run_id=str(request_id))

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
        plan = validate_and_normalize_plan(plan, config)
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
    """Convert and validate plan payload; raise ValueError if invalid. Returns normalized plan."""
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
        steps.append(Step(
            step_index=step_index or 0,
            agent_name=agent_name,
            task_description=task_description,
            depends_on=s.get("depends_on") or [],
            parallel_group=s.get("parallel_group"),
        ))
    plan = Plan(steps=steps)
    return validate_and_normalize_plan(plan, config)


async def _emit_run_event(env: dict, run_id: str, event_type: str, payload: dict | None = None) -> None:
    """Append event to run_events (no-op if migration 003 not applied)."""
    conn = await open_app_db_connection(env)
    try:
        await append_run_event(conn, run_id, event_type, payload)
    finally:
        await conn.close()


def _build_context_from_step_results(query: str, step_results: list[StepResult], plan: Plan) -> str:
    """Build context string from query and step results (for next step or resume)."""
    parts = [f"Original query: {query}"]
    for sr in step_results:
        parts.append(f"Step {sr.step_index} ({sr.agent_name}): {sr.output}")
    return "\n".join(parts)


async def _run_execute_only(request_id: uuid.UUID, query: str, plan: Plan, config, env: dict):
    """Run plan step-by-step; pause and set awaiting_user_input if an agent returns requires_validation."""
    run_id_str = str(request_id)
    try:
        await _emit_run_event(env, run_id_str, "PLAN_CREATED", {"steps": len(plan.steps)})
        step_results: list[StepResult] = []
        ordered_steps = topological_order(plan.steps)
        step_by_idx = {s.step_index: s for s in ordered_steps}
        for step in ordered_steps:
            step_id = f"S{step.step_index}"
            await _emit_run_event(env, run_id_str, "STEP_STARTED", {"step_id": step_id, "agent": step.agent_name, "task": step.task_description[:200]})
            context = _build_context_from_step_results(query, step_results, plan)
            sr, validation_payload = await run_step(step, context, config, run_id=run_id_str)
            conn = await open_app_db_connection(env)
            try:
                step_cfg = step_by_idx.get(step.step_index)
                task_desc = step_cfg.task_description if step_cfg else ""
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
            await _emit_run_event(env, run_id_str, "STEP_FINISHED" if sr.status == "success" else "STEP_FAILED", {"step_id": step_id, "agent": step.agent_name, "status": sr.status})
            if validation_payload and isinstance(validation_payload, dict):
                conn = await open_app_db_connection(env)
                try:
                    await update_request_paused(conn, request_id, step.step_index, json.dumps(validation_payload))
                finally:
                    await conn.close()
                log.info("Paused at step %s for user validation", step.step_index)
                return
            step_results.append(sr)
        final_answer = synthesize_final_answer(query, step_results)
        log.info("FINAL ANSWER: %s", (final_answer[:300] + "…") if final_answer and len(final_answer) > 300 else (final_answer or "(empty)"))
        await _update_status(env, request_id, "completed", final_answer=final_answer)
        await _emit_run_event(env, run_id_str, "RUN_FINISHED", {"status": "completed"})
    except Exception as e:
        log.exception("Execute failed")
        await _update_status(env, request_id, "failed", error_message=str(e))
        await _emit_run_event(env, run_id_str, "RUN_FINISHED", {"status": "failed", "error": str(e)})


async def _run_resume(request_id: uuid.UUID, user_response_str: str, config, env: dict):
    """Resume after user responded to validation: re-invoke paused step with user response in context, then continue."""
    try:
        conn = await open_app_db_connection(env)
        try:
            req = await get_request(conn, request_id)
            plan = await get_plan(conn, request_id)
            existing = await get_step_results(conn, request_id)
        finally:
            await conn.close()
        if not req or req.get("status") != "awaiting_user_input":
            log.warning("Resume called but request %s not awaiting_user_input", request_id)
            return
        paused_at = req.get("paused_at_step")
        if paused_at is None:
            return
        plan = plan or Plan(steps=[])
        step_by_idx = {s.step_index: s for s in plan.steps}
        step = step_by_idx.get(paused_at)
        if not step:
            await _update_status(env, request_id, "failed", error_message="Invalid paused step")
            return
        # Build context from existing step_results (excluding the paused step's current result)
        step_results_so_far: list[StepResult] = []
        for r in existing:
            if r["step_index"] == paused_at:
                continue
            out = r.get("output_payload")
            if isinstance(out, str):
                try:
                    out = json.loads(out) if out.strip().startswith("{") else out
                except (json.JSONDecodeError, AttributeError):
                    pass
            step_results_so_far.append(StepResult(
                step_index=r["step_index"],
                agent_name=r["agent_name"],
                output=out if out is not None else "",
                status=r.get("status", "success"),
                latency_ms=r.get("latency_ms"),
            ))
        context = _build_context_from_step_results(req["query"], step_results_so_far, plan)
        context += f"\n\nUser response: {user_response_str}"
        sr, validation_payload = await run_step(step, context, config, run_id=str(request_id))
        conn = await open_app_db_connection(env)
        try:
            await update_step_result(conn, request_id, paused_at, step.agent_name, sr.output, sr.status, sr.latency_ms)
            await update_request_clear_paused(conn, request_id)
            await update_request_final(conn, request_id, "running")
        finally:
            await conn.close()
        if validation_payload:
            conn = await open_app_db_connection(env)
            try:
                await update_request_paused(conn, request_id, step.step_index, json.dumps(validation_payload))
            finally:
                await conn.close()
            return
        step_results_so_far.append(sr)
        # Continue from steps that come after the paused step in dependency order.
        ordered_steps = topological_order(plan.steps)
        try:
            paused_pos = next(i for i, s in enumerate(ordered_steps) if s.step_index == paused_at)
        except StopIteration:
            await _update_status(env, request_id, "failed", error_message="Paused step not present in plan")
            return
        rest_steps = ordered_steps[paused_pos + 1:]
        for step in rest_steps:
            context = _build_context_from_step_results(req["query"], step_results_so_far, plan)
            sr, validation_payload = await run_step(step, context, config, run_id=str(request_id))
            conn = await open_app_db_connection(env)
            try:
                task_desc = step.task_description
                await save_step_result(conn, request_id, sr.step_index, sr.agent_name, {"task": task_desc}, sr.output, sr.status, sr.latency_ms)
            finally:
                await conn.close()
            if validation_payload:
                conn = await open_app_db_connection(env)
                try:
                    await update_request_paused(conn, request_id, step.step_index, json.dumps(validation_payload))
                finally:
                    await conn.close()
                return
            step_results_so_far.append(sr)
        final_answer = synthesize_final_answer(req["query"], step_results_so_far)
        await _update_status(env, request_id, "completed", final_answer=final_answer)
    except Exception as e:
        log.exception("Resume failed")
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


def _respond_request_to_str(body: RespondRequest, validation_payload: dict | None) -> str:
    """Convert user's response body to a short string for context."""
    if body.free_text and (body.free_text or "").strip():
        return (body.free_text or "").strip()
    if body.accepted is not None:
        return "User accepted." if body.accepted else "User rejected."
    if body.choice is not None and str(body.choice).strip():
        return f"User chose: {body.choice.strip()}"
    if body.choice_index is not None and validation_payload and isinstance(validation_payload.get("options"), list):
        opts = validation_payload["options"]
        idx = int(body.choice_index)
        if 0 <= idx < len(opts):
            return f"User chose: {opts[idx]}"
        return f"User chose index: {idx}"
    return "User responded."


@app.post("/request/{request_id}/respond")
async def respond_to_validation(request_id: str, body: RespondRequest, conn=Depends(get_app_db)):
    """Submit user's response to a validation request; resumes the run. Returns 202 + request_id; poll GET /request/{id}."""
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")
    req = await get_request(conn, rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.get("status") != "awaiting_user_input":
        raise HTTPException(status_code=409, detail=f"Request not awaiting user input (status: {req.get('status')})")
    validation_payload = req.get("validation_payload")
    user_response_str = _respond_request_to_str(body, validation_payload)
    config = get_config()
    env = dict(os.environ)
    await update_request_clear_paused(conn, rid)
    await update_request_final(conn, rid, "running")
    asyncio.create_task(_run_resume(rid, user_response_str, config, env))
    return JSONResponse(status_code=202, content={"request_id": request_id})


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
        plan = validate_and_normalize_plan(plan, config)
        for i, s in enumerate(plan.steps, 1):
            log.info("PLAN step %s → %s: %s", i, s.agent_name, (s.task_description[:80] + "…") if len(s.task_description) > 80 else s.task_description)
        conn = await open_app_db_connection(env)
        try:
            await save_plan(conn, request_id, plan)
        finally:
            await conn.close()

        context_parts = [f"Original query: {query}"]
        step_results: list[StepResult] = []
        for step in topological_order(plan.steps):
            context = "\n".join(context_parts)
            sr, _ = await run_step(step, context, config, run_id=str(request_id))
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
