-- Minimal schema for multi-agent orchestrator: requests, plans, step_results only.
CREATE SCHEMA IF NOT EXISTS app;

-- One row per query run
CREATE TABLE IF NOT EXISTS app.requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id VARCHAR(128) NOT NULL,
    query TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    final_answer TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_requests_domain_id ON app.requests(domain_id);
CREATE INDEX IF NOT EXISTS idx_requests_created_at ON app.requests(created_at DESC);

-- Plan (steps) per request
CREATE TABLE IF NOT EXISTS app.plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL UNIQUE REFERENCES app.requests(id) ON DELETE CASCADE,
    steps JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plans_request_id ON app.plans(request_id);

-- Step results (each agent call)
CREATE TABLE IF NOT EXISTS app.step_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES app.requests(id) ON DELETE CASCADE,
    step_index INT NOT NULL,
    agent_name VARCHAR(128) NOT NULL,
    input_payload JSONB,
    output_payload JSONB,
    status VARCHAR(32) NOT NULL DEFAULT 'success',
    latency_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_step_results_request_id ON app.step_results(request_id);
