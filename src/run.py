"""
Public library API: run a full query (plan → execute → report) without starting the web app.

Use run_query() for file-based config (local) or run_query_with_config() for
programmatic config (tests, serverless). Both return a RunResult.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from src.core.config.loader import load_domain_config
from src.core.config.models import DomainConfig
from src.core.contracts.orchestrator import StepResult
from src.core.exceptions import ConfigError
from src.data_access.factory import build_clients
from src.orchestrator.executor import run_plan
from src.orchestrator.plan_validation import validate_and_normalize_plan
from src.orchestrator.planner import build_plan
from src.orchestrator.reporter import synthesize_final_answer


class RunResult:
    """Result of a library-run query (no app DB required)."""

    def __init__(
        self,
        request_id: str,
        status: str,
        final_answer: str | None = None,
        step_results: list[StepResult] | None = None,
        error: str | None = None,
    ):
        self.request_id = request_id
        self.status = status  # "completed" | "failed" | "partial"
        self.final_answer = final_answer
        self.step_results = step_results or []
        self.error = error


def run_query(
    config_path: str | Path,
    query: str,
    project_root: Path | None = None,
    env_overrides: dict[str, str] | None = None,
) -> RunResult:
    """Run a full query using file-based domain config (local default).

    Loads config from config_path (relative to project_root if not absolute),
    builds clients, plans, executes via HTTP to agents, synthesizes final answer.
    Does not use the app DB; request_id is a new UUID for this run.

    Raises ConfigError if config is invalid. Returns RunResult with status
    "failed" or "partial" and error set if plan/execute/synthesize fails.
    """
    config = load_domain_config(config_path, project_root=project_root, env_overrides=env_overrides)
    return run_query_with_config(
        config,
        query,
        clients=None,
        project_root=project_root,
    )


def run_query_with_config(
    domain_config: DomainConfig,
    query: str,
    clients: dict[str, Any] | None = None,
    project_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Run a full query with prebuilt domain config (and optional clients).

    Use when you have DomainConfig in memory (e.g. from dict, tests, or Azure).
    If clients is None, they are built from domain_config and project_root (or env).
    """
    try:
        return asyncio.run(
            async_run_query_with_config(
                domain_config,
                query,
                clients=clients,
                project_root=project_root,
                env=env,
            )
        )
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            raise RuntimeError(
                "run_query_with_config() was called from an active event loop. "
                "Use async_run_query_with_config() in async contexts."
            ) from e
        raise


async def async_run_query_with_config(
    domain_config: DomainConfig,
    query: str,
    clients: dict[str, Any] | None = None,
    project_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Async variant of run_query_with_config(). Safe to call from active event loops."""
    request_id = str(uuid.uuid4())
    if clients is None:
        clients = build_clients(domain_config, project_root=project_root, env=env)

    try:
        plan = build_plan(query, domain_config)
        plan = validate_and_normalize_plan(plan, domain_config)
    except ConfigError:
        raise
    except Exception as e:
        return RunResult(
            request_id=request_id,
            status="failed",
            error=str(e),
        )

    try:
        step_results = await run_plan(plan, query, domain_config, run_id=request_id)
    except Exception as e:
        return RunResult(
            request_id=request_id,
            status="failed",
            step_results=[],
            error=str(e),
        )

    try:
        final_answer = synthesize_final_answer(query, step_results)
    except Exception as e:
        return RunResult(
            request_id=request_id,
            status="partial",
            step_results=step_results,
            final_answer=None,
            error=str(e),
        )

    return RunResult(
        request_id=request_id,
        status="completed",
        final_answer=final_answer,
        step_results=step_results,
    )
