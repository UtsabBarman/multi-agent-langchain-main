"""Callback handler that collects tool start/end/error events for UI display."""
from __future__ import annotations

import json
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


class ValidationCaptureCallbackHandler(BaseCallbackHandler):
    """Captures when the agent calls request_user_validation; stores the payload for the orchestrator."""

    def __init__(self) -> None:
        self.validation_payload: dict[str, Any] | None = None

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized.get("name") or "").replace(" ", "_")
        if name == "request_user_validation":
            try:
                if isinstance(input_str, str) and input_str.strip().startswith("{"):
                    data = json.loads(input_str)
                elif isinstance(input_str, dict):
                    data = input_str
                else:
                    data = {"message": str(input_str), "validation_type": "confirm"}
                self.validation_payload = {
                    "message": data.get("message", "Please confirm."),
                    "validation_type": data.get("validation_type", "confirm"),
                    "options": data.get("options"),
                    "allow_reject": data.get("allow_reject", False),
                }
            except (json.JSONDecodeError, TypeError):
                self.validation_payload = {"message": str(input_str)[:500], "validation_type": "confirm", "options": None, "allow_reject": False}


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
