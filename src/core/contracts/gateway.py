from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str
    domain_id: str | None = None
    session_id: str | None = None


class QueryResponse(BaseModel):
    request_id: str
    status: str  # "completed" | "failed" | "partial" | "cancelled"
    final_answer: str | None = None
    error: str | None = None


class PlanStepPayload(BaseModel):
    step_index: int
    agent_name: str
    task_description: str


class PlanPayload(BaseModel):
    steps: list[PlanStepPayload] = Field(default_factory=list)


class PlanOnlyResponse(BaseModel):
    """Response from POST /query/plan: request created, plan ready for user approval; or simple reply (no plan)."""
    request_id: str
    status: str = "awaiting_approval"  # "awaiting_approval" | "completed" (simple reply)
    plan: dict[str, Any]  # { "steps": [ ... ] }; empty steps when status is "completed"
    final_answer: str | None = None  # Set when status is "completed" (orchestrator answered without agents)


class ExecuteRequest(BaseModel):
    """Body for POST /query/execute: run the plan (optionally edited) for a request."""
    request_id: str
    plan: PlanPayload | None = None  # If provided, use this plan (e.g. user-edited); else use stored plan.


class RespondRequest(BaseModel):
    """Body for POST /request/{id}/respond: user's response to a validation request."""
    accepted: bool | None = None  # for confirm
    choice_index: int | None = None  # for choice (0-based)
    choice: str | None = None  # for choice (option value)
    free_text: str | None = None  # for free_text
