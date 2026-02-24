from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.core.config.models import AgentConfig
from src.agent.guardrails import apply_guardrails
from src.tools.registry import get_tools


def _invoke_simple_chain(llm: Any, prompt: ChatPromptTemplate, input_text: str) -> str:
    out = (prompt | llm).invoke({"input": input_text})
    return out.content if hasattr(out, "content") else str(out)


def _invoke_agent_with_tools(llm: Any, tools: list, prompt: ChatPromptTemplate, input_text: str) -> str:
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        agent = create_tool_calling_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True)
        out = executor.invoke({"input": input_text})
        return out.get("output", str(out))
    except Exception:
        # Fallback: no tool loop, just LLM
        return _invoke_simple_chain(llm, prompt, input_text)


def build_agent(agent_config: AgentConfig, clients: dict[str, Any]) -> Any:
    """Build a LangChain agent from config and data clients."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = get_tools(agent_config.tool_names, clients)
    prompt = ChatPromptTemplate.from_messages([
        ("system", agent_config.system_prompt),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad", optional=True),
    ])

    def run_with_guardrails(input_text: str) -> str:
        if not tools:
            content = _invoke_simple_chain(llm, prompt, input_text)
        else:
            content = _invoke_agent_with_tools(llm, tools, prompt, input_text)
        return apply_guardrails(content, agent_config.guardrails)

    return run_with_guardrails
