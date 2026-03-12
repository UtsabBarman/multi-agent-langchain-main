"""Integration test: plan → executor (mocked) → reporter (mocked LLM) → final answer."""
from unittest.mock import MagicMock, patch

import pytest
from src.core.contracts.orchestrator import Plan, Step, StepResult
from src.orchestrator.plan_validation import validate_and_normalize_plan
from src.orchestrator.reporter import synthesize_final_answer


@pytest.fixture
def domain_config():
    from src.core.config.models import AgentConfig, DomainConfig
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


def test_plan_validation_integration(domain_config):
    """Validate and normalize a plan; then simulate step results."""
    plan = Plan(steps=[
        Step(step_index=1, agent_name="researcher", task_description="Find safety guidelines"),
        Step(step_index=2, agent_name="analyst", task_description="Summarize findings"),
    ])
    plan = validate_and_normalize_plan(plan, domain_config)
    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == ["S1"]


def test_reporter_synthesizes_from_step_results():
    """Reporter produces final answer from step results (mock LLM)."""
    step_results = [
        StepResult(
            step_index=1,
            agent_name="researcher",
            output={"artifacts": {"notes": "Found 3 guidelines.", "rendered_html": "<p>PPE required.</p>"}},
            status="success",
            latency_ms=100,
        ),
        StepResult(
            step_index=2,
            agent_name="analyst",
            output="Summary: key points are A and B.",
            status="success",
            latency_ms=50,
        ),
    ]
    class FakeMessage:
        content = "<p>Final report: based on the steps, here is the answer.</p>"

    with patch("src.orchestrator.reporter.ChatOpenAI") as mock_llm_cls:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = FakeMessage()
        mock_llm.return_value = FakeMessage()
        mock_llm_cls.return_value = mock_llm
        answer = synthesize_final_answer("What are the safety guidelines?", step_results)
    assert answer is not None
    assert isinstance(answer, str)
    assert "<p>Final report" in answer
