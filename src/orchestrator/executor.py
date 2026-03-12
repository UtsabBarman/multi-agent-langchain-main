"""Execute plan by calling each agent via HTTP and collecting StepResults."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

log = logging.getLogger("executor")

# Per-agent HTTP: connect 10s, read 120s. Retry up to 3 times with exponential backoff (1, 2, 4 s).
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 120.0
MAX_RETRIES = 3
RETRY_BACKOFF_SECS = (1, 2, 4)
# Circuit breaker: open after this many consecutive failures; stay open for OPEN_SECS.
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_OPEN_SECS = 60.0

from src.core.config.models import DomainConfig
from src.core.contracts.agent import AgentInvokeRequest, AgentInvokeResponse
from src.core.contracts.orchestrator import Plan, StepResult
from src.orchestrator.plan_validation import topological_order

# Circuit breaker state per agent (in-memory): closed | open | half_open
_circuit: dict[str, dict[str, Any]] = {}


def _circuit_allow(agent_name: str) -> bool:
    """Return True if we should attempt the call; False if circuit is open and we should skip."""
    now = time.monotonic()
    c = _circuit.get(agent_name)
    if not c:
        return True
    state = c.get("state", "closed")
    if state == "closed":
        return True
    if state == "half_open":
        return True
    # state == "open"
    opened_at = c.get("opened_at", 0)
    if now - opened_at >= CIRCUIT_OPEN_SECS:
        c["state"] = "half_open"
        return True
    return False


def _circuit_record_success(agent_name: str) -> None:
    c = _circuit.get(agent_name)
    if c:
        c["state"] = "closed"
        c["failure_count"] = 0


def _circuit_record_failure(agent_name: str) -> None:
    c = _circuit.get(agent_name)
    if not c:
        _circuit[agent_name] = {"state": "closed", "failure_count": 0, "opened_at": 0}
        c = _circuit[agent_name]
    c["failure_count"] = c.get("failure_count", 0) + 1
    if c["failure_count"] >= CIRCUIT_FAILURE_THRESHOLD:
        c["state"] = "open"
        c["opened_at"] = time.monotonic()
    elif c.get("state") == "half_open":
        c["state"] = "open"
        c["opened_at"] = time.monotonic()


def _step_id(step: Any) -> str:
    """Canonical step id for logs and agent request (e.g. S1, S2)."""
    return f"S{step.step_index}"


async def run_step(
    step: Any,
    context: str,
    domain_config: DomainConfig,
    run_id: str | None = None,
    base_url_template: str = "http://127.0.0.1:{port}",
) -> tuple[StepResult, dict | None]:
    agent_name = step.agent_name
    step_id = _step_id(step)
    run_id = run_id or ""
    agent = domain_config.get_agent_by_name(agent_name)
    _extra = {"run_id": run_id, "agent": agent_name, "step_id": step_id}
    if not agent:
        log.info("Agent not found", extra={**_extra, "event_type": "step_failed"})
        return StepResult(step_index=step.step_index, agent_name=agent_name, output="Agent not found", status="failed", latency_ms=None), None
    if not _circuit_allow(agent_name):
        log.warning("Skipping call (circuit breaker open)", extra={**_extra, "event_type": "circuit_open"})
        print(f"  [{step_id}] ← {agent_name}: circuit open (skipped)", flush=True)
        return StepResult(step_index=step.step_index, agent_name=agent_name, output="Circuit breaker open (agent unhealthy)", status="failed", latency_ms=None), None
    # Docker: set ORCHESTRATOR_AGENT_HOST_researcher=researcher etc. to use service names.
    # Per-agent base_url in config (e.g. Azure Function URL) overrides host:port.
    host = os.environ.get(f"ORCHESTRATOR_AGENT_HOST_{agent_name}", "127.0.0.1")
    base_url = domain_config.get_agent_base_url(agent_name, host)
    url = f"{base_url}/invoke"
    payload = AgentInvokeRequest(
        task=step.task_description,
        context=context,
        run_id=run_id,
        step_id=step_id,
    ).model_dump()
    task_preview = (step.task_description[:100] + "…") if len(step.task_description) > 100 else step.task_description
    log.info("%s", task_preview[:200], extra={**_extra, "event_type": "step_started"})
    print(f"  [{step_id}] → {agent_name}: {task_preview}", flush=True)
    start = time.perf_counter()
    timeout = httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT)
    try:
        r = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r = await client.post(url, json=payload)
                break
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BACKOFF_SECS[attempt] if attempt < len(RETRY_BACKOFF_SECS) else RETRY_BACKOFF_SECS[-1]
                    log.warning("retry attempt=%s error=%s backoff_s=%s", attempt + 1, str(e), delay, extra={**_extra, "event_type": "retry"})
                    await asyncio.sleep(delay)
                else:
                    raise
        if r is None:
            raise RuntimeError("No response after retries")
        latency_ms = int((time.perf_counter() - start) * 1000)
        if r.status_code != 200:
            _circuit_record_failure(agent_name)
            log.warning("http_status=%s latency_ms=%s", r.status_code, latency_ms, extra={**_extra, "event_type": "step_failed"})
            print(f"  [{step_id}] ← {agent_name}: HTTP {r.status_code} ({latency_ms} ms)", flush=True)
            return StepResult(step_index=step.step_index, agent_name=agent_name, output={"error": r.text}, status="failed", latency_ms=latency_ms), None
        data = r.json()
        parsed = AgentInvokeResponse.model_validate(data)
        result = parsed.result
        status = parsed.status
        requires_validation = bool(parsed.requires_validation)
        validation_payload = parsed.validation_payload if requires_validation else None
        if validation_payload is not None and hasattr(validation_payload, "model_dump"):
            validation_payload = validation_payload.model_dump()
        # Protocol v1: pass through artifacts so reporter can use structured data
        output: str | dict[str, Any]
        if parsed.artifacts is not None:
            output = {
                "result": result,
                "artifacts": parsed.artifacts,
                "tool_calls": parsed.tool_calls,
                "errors": parsed.errors,
            }
        else:
            output = result
        if validation_payload and isinstance(validation_payload, dict):
            log.info("requires_validation=true latency_ms=%s", latency_ms, extra={**_extra, "event_type": "step_finished"})
            print(f"  [{step_id}] ← {agent_name}: requires user validation ({latency_ms} ms)", flush=True)
        else:
            out_str = str(result)[:150] + "…" if len(str(result)) > 150 else str(result)
            log.info("status=%s latency_ms=%s", status, latency_ms, extra={**_extra, "event_type": "step_finished"})
            print(f"  [{step_id}] ← {agent_name}: {out_str} ({latency_ms} ms)", flush=True)
        sr = StepResult(step_index=step.step_index, agent_name=agent_name, output=output, status=status, latency_ms=latency_ms)
        _circuit_record_success(agent_name)
        return sr, validation_payload
    except Exception as e:
        _circuit_record_failure(agent_name)
        latency_ms = int((time.perf_counter() - start) * 1000)
        log.warning("error=%s latency_ms=%s", str(e), latency_ms, extra={**_extra, "event_type": "step_failed"})
        print(f"  [{step_id}] ← {agent_name}: failed {e} ({latency_ms} ms)", flush=True)
        return StepResult(step_index=step.step_index, agent_name=agent_name, output=str(e), status="failed", latency_ms=latency_ms), None


async def run_plan(
    plan: Plan,
    query: str,
    domain_config: DomainConfig,
    run_id: str | None = None,
) -> list[StepResult]:
    run_id = run_id or ""
    ordered = topological_order(plan.steps)
    results = []
    context_parts = [f"Original query: {query}"]
    for step in ordered:
        context = "\n".join(context_parts)
        sr, _ = await run_step(step, context, domain_config, run_id=run_id)
        results.append(sr)
        out = sr.output
        context_parts.append(f"Step {step.step_index} ({step.agent_name}): {out}")
    return results
