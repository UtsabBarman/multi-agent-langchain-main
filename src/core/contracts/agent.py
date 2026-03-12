from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentInvokeRequest(BaseModel):
    task: str
    context: str | dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None  # deprecated alias; use run_id
    run_id: str | None = None  # orchestrator-generated run correlation ID (same as request_id)
    step_id: str | None = None  # e.g. "S1", "S2" for step indexing in logs


class ValidationPayload(BaseModel):
    """Payload when agent requests user validation (requires_validation=True)."""
    message: str
    validation_type: str = "confirm"  # "confirm" | "choice" | "free_text"
    options: list[str] | None = None  # for choice
    allow_reject: bool = False


class AgentInvokeResponse(BaseModel):
    result: str | dict[str, Any]
    status: str  # "success" | "failed" | "requires_validation"
    latency_ms: int | None = None
    steps: list[dict[str, Any]] | None = None  # tool_start/tool_end/tool_error for UI
    requires_validation: bool = False
    validation_payload: ValidationPayload | dict[str, Any] | None = None
    # Protocol v1: optional structured artifacts (orchestrator uses these when present)
    artifacts: dict[str, Any] | None = None  # AgentArtifacts as dict
    tool_calls: list[dict[str, Any]] | None = None  # ToolCallRecord as dict
    errors: list[dict[str, Any]] | None = None  # ErrorRecord as dict
