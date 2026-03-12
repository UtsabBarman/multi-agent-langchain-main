"""Tool for agents to request user validation (choice, confirm, free text). Orchestrator will pause and show UI."""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


def create_request_user_validation_tool() -> Any:
    """Create a tool that agents can call to ask the user for input. When called, the orchestrator pauses and shows the payload."""

    @tool
    def request_user_validation(
        message: str,
        validation_type: str = "confirm",
        options: list[str] | None = None,
        allow_reject: bool = False,
    ) -> str:
        """Request input from the user. Use this when you need the user to choose among options, confirm an action, or provide a short answer.
        message: Question or prompt to show the user.
        validation_type: One of 'confirm' (yes/no), 'choice' (user picks from options), 'free_text' (user types a short answer).
        options: For validation_type='choice', list of option strings the user can pick from.
        allow_reject: If True, user can reject/cancel in addition to accepting or choosing."""
        # Tool body is a no-op; the callback captures the args and the agent response will include requires_validation.
        return "Waiting for user response."

    return request_user_validation
