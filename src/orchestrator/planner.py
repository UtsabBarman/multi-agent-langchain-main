"""Generate a Plan (steps) from user query using LLM."""
from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.core.config.models import DomainConfig
from src.core.contracts.orchestrator import Plan, Step


# In the template, only {agent_names} and {query} are variables; JSON example uses {{ }} for literal braces
SYSTEM = """You are a planner. Given a user query and a list of available agents, output a JSON plan.
Available agents: {agent_names}
Output only valid JSON with this exact structure (no markdown, no explanation):
{{ "steps": [{{ "step_index": 1, "agent_name": "<name>", "task_description": "<what to do>" }}, ...] }}
Use only agent names from the list. Order steps logically."""


def build_plan(query: str, domain_config: DomainConfig) -> Plan:
    agent_names = ", ".join(a.name for a in domain_config.agents)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM),
        ("human", "{query}"),
    ])
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | llm
    out = chain.invoke({"query": query, "agent_names": agent_names})
    text = out.content if hasattr(out, "content") else str(out)
    # Parse JSON from response (strip markdown if present)
    import json
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    data = json.loads(text)
    steps = [Step(step_index=s["step_index"], agent_name=s["agent_name"], task_description=s["task_description"]) for s in data.get("steps", [])]
    return Plan(steps=steps)
