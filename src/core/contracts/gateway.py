from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str
    domain_id: str | None = None
    session_id: str | None = None


class QueryResponse(BaseModel):
    request_id: str
    status: str  # "completed" | "failed" | "partial"
    final_answer: str | None = None
    error: str | None = None
