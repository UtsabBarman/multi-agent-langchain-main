from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentInvokeRequest(BaseModel):
    task: str
    context: str | dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class AgentInvokeResponse(BaseModel):
    result: str | dict[str, Any]
    status: str  # "success" | "failed"
    latency_ms: int | None = None
    steps: list[dict[str, Any]] | None = None  # tool_start/tool_end/tool_error for UI
