"""Optional structured JSON logging. Set LOG_FORMAT=json to enable."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone


class StructuredJsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line: timestamp, run_id, agent, step_id, event_type, level, message, payload."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).isoformat()
        payload = {
            "timestamp": ts,
            "run_id": getattr(record, "run_id", "") or "",
            "agent": getattr(record, "agent", "") or "",
            "step_id": getattr(record, "step_id", "") or "",
            "event_type": getattr(record, "event_type", "") or record.levelname.lower(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        return json.dumps(payload, default=str)


def configure_log_format() -> None:
    """If LOG_FORMAT=json, set root logger to use StructuredJsonFormatter on a new handler (stdout)."""
    if os.environ.get("LOG_FORMAT", "").strip().lower() != "json":
        return
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
