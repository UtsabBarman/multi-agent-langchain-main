"""Agent Protocol v1: typed artifacts for reliable orchestration."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Fact(BaseModel):
    key: str
    value: str
    source: str = "llm"  # "db" | "retriever" | "llm"


class TableArtifact(BaseModel):
    name: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] | None = None  # optional column names


class Citation(BaseModel):
    id: str = ""
    title: str = ""
    uri: str = ""
    snippet: str = ""


class AgentArtifacts(BaseModel):
    facts: list[Fact] = Field(default_factory=list)
    tables: list[TableArtifact] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    notes: str = ""
    rendered_html: str = ""


class ToolCallRecord(BaseModel):
    tool: str
    input: dict[str, Any] = Field(default_factory=dict)
    output_ref: str = ""  # e.g. "artifact://..."


class ErrorRecord(BaseModel):
    type: str = "error"
    message: str
    retryable: bool = False


class AgentProtocolResponse(BaseModel):
    """Structured agent response; validate when agent returns artifacts."""
    run_id: str = ""
    agent: str = ""
    step_id: str = ""
    status: str = "success"  # "success" | "error"
    artifacts: AgentArtifacts = Field(default_factory=AgentArtifacts)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    errors: list[ErrorRecord] = Field(default_factory=list)


def artifacts_from_content_and_steps(
    content: str,
    steps: list[dict[str, Any]],
) -> AgentArtifacts:
    """Build artifacts from LLM content and tool steps (heuristic)."""
    facts: list[Fact] = []
    tables: list[TableArtifact] = []
    citations: list[Citation] = []
    notes = (content[:500] + "…") if len(content) > 500 else content if content else ""

    for s in steps or []:
        if s.get("type") == "tool_end":
            name = (s.get("name") or "").replace(" ", "_")
            out = s.get("output", "")
            if isinstance(out, dict):
                out_str = str(out)
            else:
                out_str = str(out)
            if name == "query_facts" and isinstance(s.get("output"), dict):
                rows = s.get("output", {}).get("rows", s.get("output", {}).get("data", []))
                if isinstance(rows, list) and rows:
                    tables.append(TableArtifact(name="query_result", rows=rows))
            elif name == "search_docs":
                if isinstance(s.get("output"), str) and s.get("output"):
                    citations.append(Citation(snippet=s.get("output", "")[:500], title=name))
            if out_str and len(out_str) < 300:
                facts.append(Fact(key=name, value=out_str[:300], source="db" if name == "query_facts" else "retriever"))

    return AgentArtifacts(
        facts=facts,
        tables=tables,
        citations=citations,
        notes=notes,
        rendered_html=content or "",
    )


def tool_calls_from_steps(steps: list[dict[str, Any]]) -> list[ToolCallRecord]:
    """Build tool_calls list from callback steps."""
    out: list[ToolCallRecord] = []
    for s in steps or []:
        if s.get("type") == "tool_start":
            name = (s.get("name") or "tool").replace(" ", "_")
            inp = s.get("input", "")
            if isinstance(inp, str) and inp.strip().startswith("{"):
                import json
                try:
                    inp = json.loads(inp)
                except json.JSONDecodeError:
                    inp = {"raw": inp}
            elif not isinstance(inp, dict):
                inp = {"raw": str(inp)}
            out.append(ToolCallRecord(tool=name, input=inp))
    return out
