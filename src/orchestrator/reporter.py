"""Synthesize final answer from step results using LLM; uses Protocol v1 artifacts when present."""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.core.contracts.orchestrator import StepResult

PROMPT = """You are a reporter. Given the user query and the results from each step, write a clear, concise final answer or report.
Do not invent information. Use only the provided step results.

Format your answer as clean HTML only. Use <p>, <h2>, <h3>, <ul>, <li>, <strong>, <em>, <br> for structure. Do not use Markdown (no # or **).

User query: {query}

Step results:
{step_results}

Write the final answer/report as HTML:"""


def _format_step_output(sr: StepResult) -> str:
    """Format one step for the reporter; use artifacts when present (Protocol v1)."""
    out = sr.output
    if isinstance(out, dict) and out.get("artifacts"):
        art = out["artifacts"]
        parts = []
        if art.get("notes"):
            parts.append(f"Notes: {art['notes']}")
        if art.get("facts"):
            for f in art["facts"]:
                k = f.get("key", "")
                v = f.get("value", "")
                parts.append(f"  - {k}: {v}")
        if art.get("tables"):
            for t in art["tables"]:
                parts.append(f"  Table {t.get('name', '')}: {len(t.get('rows', []))} rows")
        if art.get("citations"):
            for c in art["citations"]:
                parts.append(f"  Citation: {c.get('snippet', '')[:200]}")
        if art.get("rendered_html"):
            parts.append(f"Content: {art['rendered_html'][:1500]}")
        return f"Step {sr.step_index} ({sr.agent_name}):\n" + "\n".join(parts) if parts else f"Step {sr.step_index} ({sr.agent_name}): (no artifacts)"
    if isinstance(out, dict):
        return f"Step {sr.step_index} ({sr.agent_name}): {str(out)}"
    return f"Step {sr.step_index} ({sr.agent_name}): {out}"


def synthesize_final_answer(query: str, step_results: list[StepResult]) -> str:
    parts = [_format_step_output(sr) for sr in step_results]
    step_results_text = "\n\n".join(parts)
    prompt = ChatPromptTemplate.from_messages([("human", PROMPT)])
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    out = (prompt | llm).invoke({"query": query, "step_results": step_results_text})
    raw_content = out.content if hasattr(out, "content") else out
    return raw_content if isinstance(raw_content, str) else str(raw_content)
