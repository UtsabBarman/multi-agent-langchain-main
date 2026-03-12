from typing import Any

from pydantic import BaseModel, Field


class Step(BaseModel):
    step_index: int
    agent_name: str
    task_description: str
    depends_on: list[str] = Field(default_factory=list)  # step_ids e.g. ["S1"]; empty = no deps
    parallel_group: str | None = None  # optional; steps in same group can run in parallel


class Plan(BaseModel):
    steps: list[Step] = Field(default_factory=list)


class StepResult(BaseModel):
    step_index: int
    agent_name: str
    output: str | dict[str, Any]
    status: str  # "success" | "failed" | "timeout"
    latency_ms: int | None = None
