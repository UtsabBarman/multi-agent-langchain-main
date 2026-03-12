"""Unit tests for plan validation and topological order."""
import pytest
from src.core.config.models import AgentConfig, DomainConfig
from src.core.contracts.orchestrator import Plan, Step
from src.core.exceptions import ConfigError
from src.orchestrator.plan_validation import topological_order, validate_and_normalize_plan


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


def test_validate_normalize_dedupes_and_sorts(domain_config):
    plan = Plan(steps=[
        Step(step_index=2, agent_name="analyst", task_description="Analyze"),
        Step(step_index=2, agent_name="researcher", task_description="Dup"),
        Step(step_index=1, agent_name="researcher", task_description="Research"),
    ])
    out = validate_and_normalize_plan(plan, domain_config)
    assert len(out.steps) == 2
    assert [s.step_index for s in out.steps] == [1, 2]
    assert out.steps[0].agent_name == "researcher"
    assert out.steps[1].depends_on == ["S1"]


def test_validate_rejects_unknown_agent(domain_config):
    plan = Plan(steps=[Step(step_index=1, agent_name="unknown_agent", task_description="x")])
    with pytest.raises(ConfigError, match="unknown agent"):
        validate_and_normalize_plan(plan, domain_config)


def test_validate_rejects_too_many_steps(domain_config):
    plan = Plan(steps=[Step(step_index=i, agent_name="researcher", task_description="x") for i in range(25)])
    with pytest.raises(ConfigError, match="maximum"):
        validate_and_normalize_plan(plan, domain_config)


def test_topological_order():
    steps = [
        Step(step_index=1, agent_name="a", task_description="x", depends_on=[]),
        Step(step_index=2, agent_name="b", task_description="x", depends_on=["S1"]),
        Step(step_index=3, agent_name="c", task_description="x", depends_on=["S2"]),
    ]
    order = topological_order(steps)
    assert [s.step_index for s in order] == [1, 2, 3]


def test_topological_order_rejects_cycle():
    steps = [
        Step(step_index=1, agent_name="a", task_description="x", depends_on=["S2"]),
        Step(step_index=2, agent_name="b", task_description="x", depends_on=["S1"]),
    ]
    with pytest.raises(ConfigError, match="Cyclic dependency"):
        topological_order(steps)


def test_validate_rejects_missing_dependency(domain_config):
    plan = Plan(steps=[Step(step_index=1, agent_name="researcher", task_description="x", depends_on=["S9"])])
    with pytest.raises(ConfigError, match="missing step"):
        validate_and_normalize_plan(plan, domain_config)
