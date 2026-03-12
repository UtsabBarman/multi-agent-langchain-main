"""Unit tests for library API: run_query_with_config (mocked planner, executor, reporter)."""
from unittest.mock import AsyncMock, patch

from src.core.config.models import AgentConfig, DomainConfig
from src.core.contracts.orchestrator import Plan, Step, StepResult
from src.run import RunResult, run_query_with_config


def _minimal_domain_config():
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


def test_run_query_with_config_returns_completed_when_mocked():
    """run_query_with_config returns RunResult with status completed when planner, run_plan and synthesize are mocked."""
    config = _minimal_domain_config()
    plan = Plan(steps=[
        Step(step_index=1, agent_name="researcher", task_description="Research"),
        Step(step_index=2, agent_name="analyst", task_description="Analyze"),
    ])
    step_results = [
        StepResult(step_index=1, agent_name="researcher", output="Found X.", status="success", latency_ms=100),
        StepResult(step_index=2, agent_name="analyst", output="Summary: X.", status="success", latency_ms=50),
    ]

    async def fake_run_plan(*args, **kwargs):
        return step_results

    with patch("src.run.build_plan", return_value=plan), patch(
        "src.run.validate_and_normalize_plan", return_value=plan
    ), patch("src.run.run_plan", new=AsyncMock(side_effect=fake_run_plan)), patch(
        "src.run.synthesize_final_answer",
        return_value="<p>Final answer.</p>",
    ):
        result = run_query_with_config(config, "What is X?", env={})

    assert isinstance(result, RunResult)
    assert result.status == "completed"
    assert result.final_answer == "<p>Final answer.</p>"
    assert len(result.step_results) == 2
    assert result.error is None
    assert result.request_id is not None


def test_run_result_attributes():
    """RunResult has expected attributes."""
    r = RunResult(request_id="id1", status="failed", error="Something broke")
    assert r.request_id == "id1"
    assert r.status == "failed"
    assert r.error == "Something broke"
    assert r.final_answer is None
    assert r.step_results == []
