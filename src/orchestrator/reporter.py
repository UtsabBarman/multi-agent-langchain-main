"""Synthesize final answer from step results using LLM."""
from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.core.contracts.orchestrator import StepResult


PROMPT = """You are a reporter. Given the user query and the results from each step, write a clear, concise final answer or report.
Do not invent information. Use only the provided step results.

User query: {query}

Step results:
{step_results}

Write the final answer/report:"""


def synthesize_final_answer(query: str, step_results: list[StepResult]) -> str:
    parts = []
    for sr in step_results:
        out = sr.output
        if isinstance(out, dict):
            out = str(out)
        parts.append(f"Step {sr.step_index} ({sr.agent_name}): {out}")
    step_results_text = "\n\n".join(parts)
    prompt = ChatPromptTemplate.from_messages([("human", PROMPT)])
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    out = (prompt | llm).invoke({"query": query, "step_results": step_results_text})
    return out.content if hasattr(out, "content") else str(out)
