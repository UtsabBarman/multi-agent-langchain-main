"""Unit tests for planner (with mocked LLM)."""
from src.core.contracts.orchestrator import Plan, Step


def test_plan_parsing_from_json():
    """Test that plan steps are parsed correctly from LLM-like JSON."""
    data = {
        "steps": [
            {"step_index": 1, "agent_name": "researcher", "task_description": "Find safety info"},
            {"step_index": 2, "agent_name": "analyst", "task_description": "Summarize"},
        ]
    }
    steps = [Step(**s) for s in data["steps"]]
    plan = Plan(steps=steps)
    assert len(plan.steps) == 2
    assert plan.steps[0].agent_name == "researcher"
    assert plan.steps[1].task_description == "Summarize"
