from typing import Any

from pydantic import BaseModel, Field


class Step(BaseModel):
    step_index: int
    agent_name: str
    task_description: str


class Plan(BaseModel):
    steps: list[Step] = Field(default_factory=list)


class StepResult(BaseModel):
    step_index: int
    agent_name: str
    output: str | dict[str, Any]
    status: str  # "success" | "failed" | "timeout"
    latency_ms: int | None = None
