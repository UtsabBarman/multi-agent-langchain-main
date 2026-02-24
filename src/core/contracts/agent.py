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
