"""Execute plan by calling each agent via HTTP and collecting StepResults."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger("executor")

from src.core.config.models import DomainConfig
from src.core.contracts.orchestrator import Plan, StepResult
from src.core.contracts.agent import AgentInvokeRequest, AgentInvokeResponse


async def run_step(
    step: Any,
    context: str,
    domain_config: DomainConfig,
    base_url_template: str = "http://127.0.0.1:{port}",
) -> StepResult:
    agent_name = step.agent_name
    agent = domain_config.get_agent_by_name(agent_name)
    if not agent:
        return StepResult(step_index=step.step_index, agent_name=agent_name, output="Agent not found", status="failed", latency_ms=None)
    url = f"http://127.0.0.1:{agent.port}/invoke"
    payload = AgentInvokeRequest(task=step.task_description, context=context).model_dump()
    task_preview = (step.task_description[:100] + "…") if len(step.task_description) > 100 else step.task_description
    log.info("→ %s: %s", agent_name, task_preview)
    print(f"  [step {step.step_index}] → {agent_name}: {task_preview}", flush=True)
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload)
        latency_ms = int((time.perf_counter() - start) * 1000)
        if r.status_code != 200:
            log.warning("← %s: HTTP %s (%s ms)", agent_name, r.status_code, latency_ms)
            print(f"  [step {step.step_index}] ← {agent_name}: HTTP {r.status_code} ({latency_ms} ms)", flush=True)
            return StepResult(step_index=step.step_index, agent_name=agent_name, output={"error": r.text}, status="failed", latency_ms=latency_ms)
        data = r.json()
        result = data.get("result", data)
        status = data.get("status", "success")
        out_str = str(result)[:150] + "…" if len(str(result)) > 150 else str(result)
        log.info("← %s: %s (%s ms)", agent_name, out_str, latency_ms)
        print(f"  [step {step.step_index}] ← {agent_name}: {out_str} ({latency_ms} ms)", flush=True)
        return StepResult(step_index=step.step_index, agent_name=agent_name, output=result, status=status, latency_ms=latency_ms)
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        log.warning("← %s: failed %s (%s ms)", agent_name, e, latency_ms)
        print(f"  [step {step.step_index}] ← {agent_name}: failed {e} ({latency_ms} ms)", flush=True)
        return StepResult(step_index=step.step_index, agent_name=agent_name, output=str(e), status="failed", latency_ms=latency_ms)


async def run_plan(
    plan: Plan,
    query: str,
    domain_config: DomainConfig,
) -> list[StepResult]:
    results = []
    context_parts = [f"Original query: {query}"]
    for step in plan.steps:
        context = "\n".join(context_parts)
        sr = await run_step(step, context, domain_config)
        results.append(sr)
        # Append this step's output for next steps
        out = sr.output
        context_parts.append(f"Step {step.step_index} ({step.agent_name}): {out}")
    return results
