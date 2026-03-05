-- SQLite schema for multi-agent orchestrator: app_requests, app_plans, app_step_results.
-- Use this when SQLITE_APP_PATH (or DATABASE_URL=sqlite:///...) is set.

-- One row per query run
CREATE TABLE IF NOT EXISTS app_requests (
    id TEXT PRIMARY KEY,
    domain_id VARCHAR(128) NOT NULL,
    query TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    final_answer TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_requests_domain_id ON app_requests(domain_id);
CREATE INDEX IF NOT EXISTS idx_requests_created_at ON app_requests(created_at DESC);

-- Plan (steps) per request
CREATE TABLE IF NOT EXISTS app_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE REFERENCES app_requests(id) ON DELETE CASCADE,
    steps TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_plans_request_id ON app_plans(request_id);

-- Step results (each agent call)
CREATE TABLE IF NOT EXISTS app_step_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES app_requests(id) ON DELETE CASCADE,
    step_index INT NOT NULL,
    agent_name VARCHAR(128) NOT NULL,
    input_payload TEXT,
    output_payload TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'success',
    latency_ms INT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_step_results_request_id ON app_step_results(request_id);
