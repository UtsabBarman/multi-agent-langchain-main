"""Callback handler that collects tool start/end/error events for UI display."""
from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


class ThoughtCollectorCallbackHandler(BaseCallbackHandler):
    """Collects tool calls into a list of steps for returning in the API and showing in the UI."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self._current_tool: str | None = None

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized.get("name") or "tool").replace(" ", "_")
        self._current_tool = name
        self.steps.append({"type": "tool_start", "name": name, "input": input_str})

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        name = self._current_tool or "tool"
        self._current_tool = None
        out_str = output if isinstance(output, str) else str(output)
        self.steps.append({"type": "tool_end", "name": name, "output": out_str})

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        name = self._current_tool or "tool"
        self._current_tool = None
        self.steps.append({"type": "tool_error", "name": name, "error": str(error)})
