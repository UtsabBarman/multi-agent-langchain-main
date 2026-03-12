"""Base type for app DB connection (used by backends)."""
from __future__ import annotations

from typing import Any, Protocol


class AppDbConnectionBase(Protocol):
    requests_table: str
    plans_table: str
    step_results_table: str
    run_events_table: str  # "run_events"

    async def execute(self, sql: str, *params: Any) -> None: ...
    async def fetchrow(self, sql: str, *params: Any) -> dict[str, Any] | None: ...
    async def fetch(self, sql: str, *params: Any) -> list[dict[str, Any]]: ...
    async def close(self) -> None: ...
