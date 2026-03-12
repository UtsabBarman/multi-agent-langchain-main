"""Unit tests for executor: run_step, run_plan, circuit breaker, retries."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.core.config.models import AgentConfig, DomainConfig
from src.core.contracts.orchestrator import Plan, Step
from src.orchestrator import executor as executor_module
from src.orchestrator.executor import _step_id, run_plan, run_step


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def domain_config():
    return DomainConfig(
        domain_id="test",
        domain_name="Test",
        env_file_path=".env",
        orchestrator=AgentConfig(name="orch", port=8000, system_prompt="x", guardrails=[], tool_names=[]),
        agents=[
            AgentConfig(name="researcher", port=8001, system_prompt="x", guardrails=[], tool_names=[]),
            AgentConfig(name="analyst", port=8002, system_prompt="x", guardrails=[], tool_names=[]),
        ],
        data_sources=[],
    )


@pytest.fixture(autouse=True)
def reset_circuit():
    """Reset circuit breaker state between tests to avoid leakage."""
    executor_module._circuit.clear()
    yield
    executor_module._circuit.clear()


def test_step_id():
    step = Step(step_index=1, agent_name="a", task_description="t")
    assert _step_id(step) == "S1"


def test_run_step_agent_not_found(domain_config):
    async def _():
        step = Step(step_index=1, agent_name="nonexistent", task_description="Do something")
        sr, v = await run_step(step, "context", domain_config, run_id="run-1")
        assert sr.status == "failed"
        assert "Agent not found" in str(sr.output)
        assert v is None
    _run(_())


def test_run_step_success_returns_artifacts(domain_config):
    async def _():
        step = Step(step_index=1, agent_name="researcher", task_description="Research X")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": "Found data.",
            "status": "success",
            "artifacts": {"facts": [], "notes": "Done", "rendered_html": "<p>Done</p>"},
        }
        with patch("src.orchestrator.executor.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            sr, v = await run_step(step, "context", domain_config, run_id="run-1")
        assert sr.status == "success"
        assert isinstance(sr.output, dict)
        assert sr.output.get("artifacts") is not None
        assert v is None
    _run(_())


def test_run_step_http_error_records_failure(domain_config):
    async def _():
        step = Step(step_index=1, agent_name="researcher", task_description="Research")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"
        with patch("src.orchestrator.executor.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            sr, _ = await run_step(step, "context", domain_config, run_id="run-1")
        assert sr.status == "failed"
        assert executor_module._circuit.get("researcher", {}).get("failure_count") == 1
    _run(_())


def test_circuit_opens_after_failures(domain_config):
    """After CIRCUIT_FAILURE_THRESHOLD failures, next call is skipped (circuit open)."""
    async def _():
        step = Step(step_index=1, agent_name="researcher", task_description="Research")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"
        with patch("src.orchestrator.executor.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            for _ in range(executor_module.CIRCUIT_FAILURE_THRESHOLD):
                sr, _ = await run_step(step, "context", domain_config, run_id="run-1")
                assert sr.status == "failed"
        post_mock = AsyncMock()
        with patch("src.orchestrator.executor.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = post_mock
            sr, _ = await run_step(step, "context", domain_config, run_id="run-1")
        assert sr.status == "failed"
        assert "Circuit breaker open" in str(sr.output)
        assert post_mock.call_count == 0
    _run(_())


def test_run_plan_uses_topological_order(domain_config):
    """run_plan executes steps in dependency order."""
    async def _():
        plan = Plan(steps=[
            Step(step_index=2, agent_name="analyst", task_description="Analyze", depends_on=["S1"]),
            Step(step_index=1, agent_name="researcher", task_description="Research", depends_on=[]),
        ])
        call_order = []

        async def mock_post(*args, **kwargs):
            call_order.append(kwargs.get("json", {}).get("step_id", "?"))
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {"result": "ok", "status": "success"}
            return r

        with patch("src.orchestrator.executor.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=mock_post)
            results = await run_plan(plan, "query", domain_config, run_id="run-1")
        assert len(results) == 2
        assert call_order == ["S1", "S2"]
    _run(_())
