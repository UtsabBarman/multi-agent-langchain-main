-- Append-only event log for runs (observability, replay, SSE).
-- Run after 002_add_validation_columns.sql.

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_events_run_id_ts ON run_events(run_id, ts);
