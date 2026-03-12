# Roadmap: From Demo to Production Runtime

This document captures the evolution of the multi-agent system: deliverables, phases, repo structure, versioning, and priorities.

---

## Deliverables (Foundation)

### Unified Run ID + Step ID everywhere

- Orchestrator generates `run_id`; every agent request includes it.
- Every log line includes `run_id`, `agent`, `step_id`.

### Hard timeouts + retries (critical)

- Per-agent HTTP timeout (connect + read).
- Retry policy with exponential backoff.
- Circuit breaker per agent (if unhealthy, skip/fallback).

### Structured logs (JSON logs)

- Fields: `timestamp`, `run_id`, `agent`, `step_id`, `event_type`, `payload`.
- Enables search and correlation.

### Config validation

- On startup: validate domain config, port uniqueness, tool availability, schema compatibility.
- Fail fast.

**Definition of done (foundation):** Runs don’t hang, failures are explainable, logs are searchable, configs don’t silently misconfigure.

---

## Phase 1 — Agent Protocol v1 (highest leverage)

**Problem:** Agents output “HTML text” and the orchestrator concatenates strings → reliability and quality suffer.

### Design: Agent Protocol v1 (typed + artifacts)

Every agent returns a structured payload, e.g.:

```json
{
  "run_id": "uuid",
  "agent": "db_agent",
  "step_id": "S2",
  "status": "success|error",
  "artifacts": {
    "facts": [{ "key": "...", "value": "...", "source": "db|retriever|llm" }],
    "tables": [{ "name": "...", "rows": [...], "schema": [...] }],
    "citations": [{ "id": "...", "title": "...", "uri": "...", "snippet": "..." }],
    "notes": "short reasoning summary (non-sensitive)",
    "rendered_html": "<div>optional</div>"
  },
  "tool_calls": [{ "tool": "...", "input": {...}, "output_ref": "artifact://..." }],
  "errors": [{ "type": "...", "message": "...", "retryable": true }]
}
```

### Orchestrator changes

- Reasoning uses **artifacts**, not pasted text.
- “Reporter” step: render artifacts → final answer (HTML/Markdown).
- Schema validation on every agent response (Pydantic / JSON Schema).

**Definition of done:** Orchestration quality doesn’t collapse when an agent writes slightly different wording; final report is built from structured data.

---

## Phase 2 — Planning/execution as a real control-plane

### 2A) Planning: validated + policy-driven

- JSON schema validation of plan.
- Retry if invalid plan.
- Plan normalization (dedupe, enforce max steps).
- Policy checks (e.g. “db agent must run before analysis agent” if required).
- Optional deterministic templates for common request types.

### 2B) Execution: DAG-capable + parallel

**Step model additions:**

- `depends_on`: `[step_id...]`
- `parallel_group`: `"A"` (optional)
- `inputs`: `{ artifact_refs... }`

**Executor:**

- Topologically sort DAG.
- Run independent steps concurrently with a worker pool.
- Enforce concurrency limits per agent/tool.

**Definition of done:** Multi-step workflows run faster and more reliably; plans can’t break execution.

---

## Phase 3 — Observability & live UI

### Streaming run events (must-have)

- **Endpoint:** `GET /runs/{run_id}/events` via SSE (or WebSockets).
- Agents push events to orchestrator (or orchestrator streams what it receives).
- **Event types:** `PLAN_CREATED`, `STEP_STARTED`, `TOOL_CALLED`, `STEP_FINISHED`, `STEP_FAILED`, `RUN_FINISHED`.

### Store traces cleanly

- Move from “step_results table” to append-only **event log**:
  - `run_events(run_id, ts, event_type, payload_json)`.
- Becomes replay mechanism, UI feed, and debugging tool.

**Definition of done:** Open a run and watch it live; replay it later exactly.

---

## Phase 4 — Production persistence, multi-user, deployment

### Storage

- Keep SQLite for local/dev.
- Add Postgres support for production (same schema + migrations).
- **Artifact store:** small artifacts in DB; large in filesystem or S3-compatible (e.g. MinIO).

### Deployment

- Provide `docker-compose.yml`: orchestrator + N agents + Postgres + optional Redis + optional MinIO.
- Each service has health checks.
- Config/secrets via env vars.

### Auth & rate limiting

- API key / JWT auth on orchestrator endpoints.
- Rate limit per key (basic sliding window).
- CORS rules for UI.

**Definition of done:** One command deploys the stack; multiple users can run queries safely.

---

## Phase 5 — Tool governance, safety, enterprise hardening

### Tool permission model

- Config declares: which agent can call which tool.
- Tool-level constraints: read-only DB, max rows, allowed tables, max tokens, allowed domains.

### Sandboxing & guardrails that enforce

- **DB tool:** schema-aware query builder or SQL AST validation (not “startswith SELECT”).
- **Retriever:** enforce k, metadata filters, maximum chunk size.
- **Output safety:** HTML sanitization (or Markdown + safe rendering); secrets redaction; prompt-injection defenses for retrieval (filtering/quoting).

**Definition of done:** Tool misuse is prevented by code, not only by prompt instructions.

---

## Phase 6 — Testing, evaluation, release engineering

### Testing stack

- **Unit:** planner parsing, executor DAG logic, protocol validation, tool wrappers.
- **Integration:** spin orchestrator + agents in test mode; mock LLM; 5–20 golden workflows end-to-end.
- **Regression/evals:** fixed prompts + fixed tool outputs → expected artifacts; score format, citations, correctness.

### CI/CD

- Ruff + mypy + pytest.
- Docker build + push (tags).
- Release: bump version, changelog, publish to PyPI.

**Definition of done:** Every PR proves the system still works; releases are repeatable.

---

## Recommended repo structure (clean package boundary)

```
src/
  runtime/
    protocol/          # Pydantic schemas, artifact refs
    planner/           # Plan models, validation, templates
    executor/          # DAG, retry, timeouts, concurrency
    events/            # Event bus, SSE/WS streaming
    security/          # Auth, rate limits, redaction
    storage/           # DB, migrations, artifact store
  orchestrator_app/    # FastAPI app wiring
  agent_app/          # Agent FastAPI app wiring
  tools/               # Tool registry + implementations
  ui/                  # Optional (or separate package)
```

---

## Versioning path

| Version | Focus |
|--------|--------|
| **v0.3** | run_id/step_id, timeouts/retries, structured logs, config validation |
| **v0.4** | Agent Protocol v1 + structured artifacts |
| **v0.5** | DAG + concurrency + event log + SSE streaming |
| **v0.6** | docker-compose + Postgres + auth |
| **v0.7** | Tool permissions + stronger guardrails |
| **v1.0** | Tests/evals + release pipeline + stable API |

---

## If you only do 3 things next

1. **Agent Protocol v1** (structured artifacts) — reliability and quality of orchestration.
2. **Event log + SSE streaming** — true observability and live UI.
3. **Validated planner + DAG executor** — reliability and speed.

These three upgrades move the system from “prompt-driven demo” to a real runtime.
