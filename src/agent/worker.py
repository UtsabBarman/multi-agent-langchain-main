from __future__ import annotations

from typing import Any, cast

from langchain_classic.agents import AgentExecutor
from langchain_classic.agents.tool_calling_agent.base import create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from src.agent.callbacks import ThoughtCollectorCallbackHandler, ValidationCaptureCallbackHandler
from src.agent.guardrails import apply_guardrails
from src.core.config.models import AgentConfig
from src.tools.registry import get_tools


def _invoke_simple_chain(llm: Any, prompt: ChatPromptTemplate, input_text: str) -> str:
    out = (prompt | llm).invoke({"input": input_text})
    raw_content = out.content if hasattr(out, "content") else out
    return raw_content if isinstance(raw_content, str) else str(raw_content)


def _invoke_agent_with_tools(
    llm: Any,
    tools: list,
    prompt: ChatPromptTemplate,
    input_text: str,
    callback_handler: ThoughtCollectorCallbackHandler | None = None,
    validation_capture: ValidationCaptureCallbackHandler | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Returns (output_text, validation_payload or None)."""
    try:
        agent = create_tool_calling_agent(llm, tools, prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=30,
            early_stopping_method="generate",
        )
        callbacks = [c for c in (callback_handler, validation_capture) if c is not None]
        config: RunnableConfig | None = cast(RunnableConfig, {"callbacks": callbacks}) if callbacks else None
        out = executor.invoke({"input": input_text}, config=config)
        output = out.get("output", str(out))
        payload = validation_capture.validation_payload if validation_capture else None
        return output, payload
    except Exception as e:
        # Surface tool execution failures to caller instead of silently degrading to plain LLM output.
        raise RuntimeError(f"Tool-enabled agent execution failed: {e}") from e


def build_agent(agent_config: AgentConfig, clients: dict[str, Any]) -> Any:
    """Build a LangChain agent from config and data clients."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = get_tools(agent_config.tool_names, clients)
    prompt = ChatPromptTemplate.from_messages([
        ("system", agent_config.system_prompt),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad", optional=True),
    ])

    def run_with_guardrails(input_text: str) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        if not tools:
            content = _invoke_simple_chain(llm, prompt, input_text)
            return apply_guardrails(content, agent_config.guardrails), [], None
        collector = ThoughtCollectorCallbackHandler()
        validation_capture = ValidationCaptureCallbackHandler()
        content, validation_payload = _invoke_agent_with_tools(
            llm, tools, prompt, input_text, callback_handler=collector, validation_capture=validation_capture
        )
        return apply_guardrails(content, agent_config.guardrails), collector.steps, validation_payload

    return run_with_guardrails
