# Multi-Agent LangChain

A config-driven multi-agent framework built with FastAPI and LangChain. An orchestrator receives a user query, plans a multi-step workflow, delegates steps to specialist agents over HTTP, lets agents use tools backed by SQLite and Chroma, and synthesizes a final HTML answer.

The project can be used in three ways:

- as a **web app** with a plan-approval UI
- as a **CLI-backed local stack**
- as a **Python library** for running config-driven multi-agent workflows from code

The sample domain in this repository is **manufacturing**, but the design is meant to be adapted to other domains mostly through configuration rather than code changes.

---

## Overview

### What this project gives you

- A central **Orchestrator** service that plans, validates, executes, and reports.
- Multiple **Agent** services with role-specific prompts, guardrails, and allowed tools.
- A **config-driven model** for defining domains, agents, tools, and data sources.
- A built-in **web UI**, **CLI**, and **library API**.
- Support for:
  - step planning
  - dependency-aware execution
  - retries and circuit breaker behavior
  - pause/resume for user validation
  - persistence of requests, plans, step results, and run events

### What it is best for

- knowledge workflows that combine retrieval, structured data, and role-specific reasoning
- domain-specific assistants that need multiple cooperating agents
- experiments where you want to swap prompts, tools, or agents via config
- local development first, with a path toward remote/serverless deployment

---

## Runtime Modes

### 1. Web App

The orchestrator serves a browser UI at `GET /`:

- submit a query
- preview and edit the plan
- approve or cancel execution
- inspect step-by-step progress
- see each agent’s latest output in iframes
- browse recent history
- upload/search docs and inspect configured DBs

The UI uses:

- `POST /query/plan` to create a plan for review
- `POST /query/execute` to run the approved plan
- `POST /request/{id}/respond` to resume paused runs

### 2. CLI

The CLI client in `scripts/query_cli.py` is a lightweight way to run the stack locally:

- sends a synchronous query to the orchestrator
- prints request ID, plan/step trace, and final answer
- supports `--trace` to inspect request/response payloads

### 3. Library

The public library API lives in `src/run.py`:

- `run_query(...)` for file-based config
- `run_query_with_config(...)` for programmatic config
- `async_run_query_with_config(...)` for async/event-loop-safe usage

Important caveat:

- **Library mode still executes steps over HTTP to agent services**, so agents must be running unless you mock execution in tests.

### Service responsibilities

- `src/orchestrator/planner.py`
  - asks an LLM to build a step plan
- `src/orchestrator/plan_validation.py`
  - validates and normalizes the plan
- `src/orchestrator/executor.py`
  - calls agents over HTTP with retries, timeout, and circuit breaker behavior
- `src/orchestrator/reporter.py`
  - creates the final response from step results
- `src/orchestrator/session.py`
  - persists requests, plans, step results, and run events
- `src/agent/main.py`
  - serves each agent API
- `src/agent/worker.py`
  - builds LangChain agents from config and tools
- `src/tools/registry.py`
  - maps tool names from config to concrete tool instances

### Runtime behavior

- Each run gets a `run_id` (same as `request_id` in app/API flows).
- Each step gets a step ID like `S1`, `S2`, etc.
- Agent HTTP execution uses:
  - 10s connect timeout
  - 120s read timeout
  - exponential backoff retries
  - in-memory circuit breaker behavior per agent
- On startup, config is validated for:
  - unique ports
  - supported data source types
  - known tools
  - duplicate agent names
- Set `LOG_FORMAT=json` for structured logs.

---

## Project Layout

```text
multi-agent-langchain/
├── config/
│   ├── domains/             # Domain JSON (e.g. manufacturing.json)
│   └── env/                 # .env and .env.example
├── data/                    # Optional local DBs, vector store, chat artifacts
├── docs/
├── migrations/versions/     # SQL migrations for the app DB
├── scripts/
│   ├── startup.py
│   ├── query_cli.py
│   ├── migrate.py
│   ├── seed_manufacturing_data.py
│   └── test_sqlite_setup.py
├── src/
│   ├── core/                # Config, contracts, exceptions, logging, env helpers
│   ├── data_access/         # SQLite + Chroma access and client building
│   ├── tools/               # Tool implementations and registry
│   ├── agent/               # Agent service and runtime
│   ├── orchestrator/        # Orchestrator API, UI, planner, executor, reporter
│   ├── gateway/             # Optional reverse proxy
│   └── run.py               # Public library API
├── tests/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

### Modularity notes

- **Env loading**: entrypoints use `ensure_project_env(...)` so `.env` can be loaded consistently.
- **App DB access**: shared through `src/data_access/app_db`.
- **Chroma indexing**: shared by the indexing tool and the orchestrator doc upload API.
- **Tools**: new tools are registered once in `src/tools/registry.py`.
- **UI templating**: orchestrator HTML is mostly in `src/orchestrator/templates/orchestrator.html`.

---

## Setup Requirements

### Python

- Python `3.11+`

### Required environment variables

Required for most real runs:

- `OPENAI_API_KEY`
- `SQLITE_APP_PATH`

Required for the sample manufacturing domain to fully work:

- `SQLITE_MANUFACTURING_PATH`
- `CHROMA_PATH`

Useful optional variables:

- `CONFIG_PATH`
- `PORT`
- `AGENT_ID`
- `ORCHESTRATOR_API_KEY`
- `LOG_FORMAT=json`
- `DOC_UPLOAD_MAX_BYTES`
- `ORCHESTRATOR_AGENT_HOST_researcher`
- `ORCHESTRATOR_AGENT_HOST_analyst`
- `ORCHESTRATOR_AGENT_HOST_writer`

### Migrations

Run `scripts/migrate.py` before using the orchestrator app/web stack.

The migration runner:

- applies SQL files from `migrations/versions`
- records applied migrations in `schema_migrations`
- stores checksums
- refuses to continue if an already-applied migration file was modified

Current schema includes:

- app requests
- app plans
- app step results
- validation/pause-resume columns
- run event logging

### Recommended startup order

1. Configure `.env`
2. Run `scripts/migrate.py`
3. Optionally run `scripts/seed_manufacturing_data.py`
4. Start the services with `scripts/startup.py`
5. Use the web UI, CLI, or API

---

## Commands

| Command | Description |
|--------|--------------|
| `PYTHONPATH=. python scripts/migrate.py` | Run DB migration once (needs `SQLITE_APP_PATH`). |
| `PYTHONPATH=. python scripts/seed_manufacturing_data.py` | Seed manufacturing SQLite + Chroma with sample data (needs `SQLITE_MANUFACTURING_PATH`, `CHROMA_PATH`, and `OPENAI_API_KEY`). |
| `PYTHONPATH=. python scripts/startup.py` | Start orchestrator + agents. Prints the UI URL. Options: `--no-kill`, `--background`, `--list-ports`, `--config <path>`. |
| `PYTHONPATH=. python scripts/query_cli.py "question"` | Send a sync query and print request/step/final answer output. |
| `PYTHONPATH=. python scripts/query_cli.py "question" --trace` | Same as above, plus full request/response tracing. |
| `PYTHONPATH=. python scripts/test_sqlite_setup.py` | Verify app DB and tool wiring without running the whole stack. |

From project root; or use `pip install -e .` and omit `PYTHONPATH=.`.

---

## Configuration Model

The main extension point is a domain JSON file such as `config/domains/manufacturing.json`.

### Domain config schema

The schema is represented in `src/core/config/models.py`.

A domain config contains:

- `domain_id`
- `domain_name`
- `env_file_path`
- `orchestrator`
- `agents`
- `data_sources`
- `session_store`

### Orchestrator and agent config

Both orchestrator and agents use the same basic shape:

- `name`
- `port`
- `system_prompt`
- `guardrails`
- `tool_names`
- optional `chat_history_path`
- optional `label`
- optional `base_url`

### Data sources

Currently supported data source types:

- relational: `type: "rel_db"` with `engine: "sqlite"`
- vector: `type: "vector_db"` with `engine: "chroma"`

Each data source points to an environment variable name via `connection_id`.

### Built-in tools

Currently registered tools:

- `query_facts`
- `search_docs`
- `index_doc`
- `request_user_validation`

Unknown tool names fail config validation.

### Minimal domain example

```json
{
  "domain_id": "manufacturing",
  "domain_name": "Windmill Manufacturing",
  "env_file_path": "config/env/.env",
  "orchestrator": {
    "name": "orchestrator",
    "port": 8000,
    "system_prompt": "Plan, delegate, and synthesize.",
    "guardrails": ["Do not skip steps."],
    "tool_names": []
  },
  "agents": [
    {
      "name": "researcher",
      "port": 8001,
      "system_prompt": "Use tools to gather facts.",
      "guardrails": ["Do not fabricate data."],
      "tool_names": ["search_docs", "query_facts", "index_doc"]
    },
    {
      "name": "writer",
      "port": 8002,
      "system_prompt": "Write the final answer clearly.",
      "guardrails": [],
      "tool_names": []
    }
  ],
  "data_sources": [
    {
      "id": "manufacturing_db",
      "type": "rel_db",
      "engine": "sqlite",
      "connection_id": "SQLITE_MANUFACTURING_PATH"
    },
    {
      "id": "docs",
      "type": "vector_db",
      "engine": "chroma",
      "connection_id": "CHROMA_PATH",
      "collection_name": "manufacturing_docs"
    }
  ],
  "session_store": {
    "type": "sqlite",
    "connection_id": "SQLITE_APP_PATH"
  }
}
```

### Full sample config

The default sample domain is in `config/domains/manufacturing.json`.

It defines:

- an orchestrator
- three agents: `researcher`, `analyst`, `writer`
- app DB, manufacturing DB, and Chroma-backed docs store

---

## Using This as a Library

The public library surface is in `src/run.py`.

### Option 1: File-based config

Use `run_query(...)` when you want the library to load config from a JSON file.

```python
from pathlib import Path

from src.run import run_query

result = run_query(
    "config/domains/manufacturing.json",
    "What are the safety guidelines for Product X?",
    project_root=Path("/path/to/multi-agent-langchain-main"),
)

print(result.request_id)
print(result.status)        # completed | failed | partial
print(result.final_answer)
for step in result.step_results:
    print(step.agent_name, step.status)
```

### Option 2: Programmatic config

Use `run_query_with_config(...)` when you already have a `DomainConfig` or want to construct config in code.

```python
import os

from src.core.config.loader import load_domain_config
from src.run import run_query_with_config

config = load_domain_config(
    {
        "domain_id": "demo",
        "domain_name": "Demo Domain",
        "env_file_path": "config/env/.env",
        "orchestrator": {
            "name": "orchestrator",
            "port": 8000,
            "system_prompt": "Plan and delegate.",
            "guardrails": [],
            "tool_names": []
        },
        "agents": [
            {
                "name": "researcher",
                "port": 8001,
                "system_prompt": "Research using tools only.",
                "guardrails": ["Do not fabricate data."],
                "tool_names": ["search_docs", "query_facts"]
            },
            {
                "name": "writer",
                "port": 8002,
                "system_prompt": "Write a concise final answer.",
                "guardrails": [],
                "tool_names": []
            }
        ],
        "data_sources": [
            {
                "id": "facts_db",
                "type": "rel_db",
                "engine": "sqlite",
                "connection_id": "SQLITE_FACTS_PATH"
            },
            {
                "id": "docs",
                "type": "vector_db",
                "engine": "chroma",
                "connection_id": "CHROMA_PATH",
                "collection_name": "demo_docs"
            }
        ],
        "session_store": {
            "type": "sqlite",
            "connection_id": "SQLITE_APP_PATH"
        }
    },
    env_overrides=os.environ,
)

result = run_query_with_config(config, "Summarize the latest policy updates.", env=os.environ)
print(result.final_answer)
```

### Option 3: Async-safe usage

Use `async_run_query_with_config(...)` inside notebooks, async servers, or existing event loops.

```python
import os

from src.core.config.loader import load_domain_config
from src.run import async_run_query_with_config

config = load_domain_config("config/domains/manufacturing.json", env_overrides=os.environ)

# inside an async function
result = await async_run_query_with_config(
    config,
    "Give me a concise safety summary for Product X.",
    env=os.environ,
)
print(result.status)
```

### Public API summary

- `run_query(config_path, query, project_root=None, env_overrides=None)`
- `run_query_with_config(domain_config, query, clients=None, project_root=None, env=None)`
- `async_run_query_with_config(domain_config, query, clients=None, project_root=None, env=None)`
- `RunResult`
  - `request_id`
  - `status`
  - `final_answer`
  - `step_results`
  - `error`

### Important caveats for library users

- File-based config loading also loads the `.env` file pointed to by `env_file_path`.
- Dict-based config loading validates config but does **not** automatically load env from file.
- `run_query_with_config(...)` should not be called from an active event loop; use `async_run_query_with_config(...)`.
- Library execution still calls agents over HTTP, so agents must be running unless mocked.

---

## How to Build Your Own Multi-Agent Domain

This repository is intended to be adapted to new use cases by editing configuration first.

### Step 1: Define the roles

Choose the agents you need, for example:

- `researcher`
- `analyst`
- `writer`
- `reviewer`
- `planner`

One process per role is a good starting point.

### Step 2: Define the data sources

For each domain, declare the structured and retrieval data your agents need.

Examples:

- SQLite facts DB
- Chroma document index
- app/session store

### Step 3: Assign tools per agent

Only give each agent the tools that role should be allowed to use.

Examples:

- researcher: `["search_docs", "query_facts"]`
- analyst: `["query_facts"]`
- writer: `[]`

### Step 4: Write prompts and guardrails

- The orchestrator prompt should explain how to plan and delegate.
- Each agent prompt should define its role and tool usage rules.
- Guardrails should be short, enforceable constraints like:
  - `Do not fabricate data.`
  - `Stick to the provided context.`
  - `Max 500 words per response.`

### Step 5: Test it

```bash
PYTHONPATH=. python scripts/startup.py --config config/domains/hr.json
PYTHONPATH=. python scripts/query_cli.py "What is our vacation policy?" --trace
```

### Example: new domain workflow

1. Create `config/domains/hr.json`
2. Add environment variables for its data sources
3. Reuse built-in tools or add new ones
4. Start with `scripts/startup.py --config ...`
5. Iterate on prompts, tools, and guardrails until behavior is correct

---

## Defining New Tools

Tools are LangChain tools that agents can call. The registry in `src/tools/registry.py` maps config tool names to concrete tool instances.

### Step 1: Implement the tool

```python
# src/tools/my_tool/thing.py
from langchain_core.tools import tool


def create_my_tool(some_client):
    @tool
    def my_tool(arg: str) -> str:
        """Describe what this tool does and when the LLM should use it."""
        return f"processed: {arg}"

    return my_tool
```

### Step 2: Register the tool

```python
from typing import Any


def _my_tool_factory(clients: dict[str, Any]) -> Any | None:
    client = clients.get("my_data_source_id")
    return create_my_tool(client) if client else None


_TOOL_FACTORIES = {
    # existing tools...
    "my_tool": _my_tool_factory,
}
```

### Step 3: Wire it into config

- add the required data source under `data_sources`
- add `"my_tool"` to the relevant agent’s `tool_names`

Agents only receive the tools listed in their own config.

---

## API Reference

## Orchestrator (default port `8000`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI with plan approval, agent iframes, history, doc store, and DB store. |
| `/health` | GET | Health check. |
| `/query` | POST | Sync query. Returns `{ request_id, status, final_answer, error? }`. |
| `/query/plan` | POST | Create request + plan for approval. |
| `/query/execute` | POST | Execute an approved or edited plan. |
| `/query/async` | POST | Start async query execution and return request ID. |
| `/request/{request_id}` | GET | Inspect request state, plan, and step results. |
| `/request/{request_id}/respond` | POST | Resume a run paused for user validation. |
| `/request/{request_id}/cancel` | POST | Cancel a request awaiting approval. |
| `/request/{request_id}` | DELETE | Delete a chat/request and related persisted state. |
| `/history` | GET | Return recent requests for the UI. |
| `/trace/last` | GET | Return the most recent request trace. |
| `/runs/{run_id}/events` | GET | Stream run events as SSE. |
| `/api/doc/collections` | GET | List Chroma collections. |
| `/api/doc/upload` | POST | Upload `.txt` or `.md` and index to Chroma. |
| `/api/db/connections` | GET | List configured DB connections. |
| `/api/db/test` | GET | Test a configured DB connection. |
| `/api/db/tables` | GET | List tables for a configured DB connection. |

## Agent (one per configured port)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Simple UI showing latest task/result/tool calls. |
| `/health` | GET | Health check. |
| `/last` | GET | Last invoke payload/result/tool steps. |
| `/invoke` | POST | Execute the agent task and return structured output. |

Agent responses may include:

- `result`
- `status`
- `latency_ms`
- `steps`
- `requires_validation`
- `validation_payload`
- structured artifacts/tool call metadata

---

## Docker

The repo includes:

- a `Dockerfile` for a single reusable image
- a `docker-compose.yml` stack for local multi-service startup

### Compose stack

The compose stack currently includes:

- `migrate`
- `orchestrator`
- `researcher`
- `analyst`
- `writer`

The `migrate` service runs first so the app DB schema exists before the orchestrator starts.

### Run with Docker Compose

```bash
docker compose up --build
```

Expected behavior:

- `migrate` runs once and exits successfully
- orchestrator and agents start afterward
- services use `./data:/data`
- service-to-service calls use Docker hostnames via `ORCHESTRATOR_AGENT_HOST_*`

---

## Serverless / Remote Agent Notes

This codebase can support remote agents through config.

### Per-agent `base_url`

Any agent can override local host/port resolution with:

```json
{
  "name": "researcher",
  "base_url": "https://my-agent.example.com"
}
```

The orchestrator will call:

- `{base_url}/invoke`

### Local vs remote config

| | Local run | Remote / serverless |
|--|-----------|---------------------|
| Config source | file path | file path, dict, App Config, Blob, Key Vault |
| Agent addressing | host + port | `base_url` |
| Data stores | local SQLite / Chroma | managed DB/vector store |
| Env | `.env` | app settings / secret store |

Local behavior remains unchanged; deployment behavior can be adapted by config.

---

## Testing and Development

### Install dev dependencies

```bash
pip install -e ".[dev]"
```

### Run checks

```bash
ruff check src tests scripts
mypy src
pytest tests/unit tests/integration -v
```

### CI notes

CI runs on Python `3.11` and `3.12`.

Current workflow includes:

- Ruff on `tests` and `scripts`
- Ruff on `src`
- mypy on `src`
- unit and integration tests

---

## Developer Guide

### Extending to a new use case

To support a new domain such as HR, support, legal, or internal docs:

1. create a new domain JSON under `config/domains/`
2. define its agents, prompts, tools, and data sources
3. set matching environment variables
4. start the stack with `--config`

Example:

```bash
PYTHONPATH=. python scripts/startup.py --config config/domains/hr.json
PYTHONPATH=. python scripts/query_cli.py "Summarize the PTO policy."
```

### Direct service startup

You can also start services manually:

```bash
PYTHONPATH=. python -m src.orchestrator.main
PYTHONPATH=. python -m src.agent.main --agent-id researcher --config-path config/domains/manufacturing.json
PYTHONPATH=. python -m src.agent.main --agent-id analyst --config-path config/domains/manufacturing.json
PYTHONPATH=. python -m src.agent.main --agent-id writer --config-path config/domains/manufacturing.json
```

---

## Caveats and Important Notes

- Library mode is **not fully in-process**. It still executes agent steps over HTTP.
- Dict-based config loading does **not** automatically load the `.env` file.
- Missing datasource env vars may lead to tools acting like no-ops rather than full startup failure.
- Only SQLite and Chroma are supported data source types today.
- `query_facts` is read-only and only supports read-only `SELECT`/`WITH` style SQL.
- Chroma indexing/search depends on embedding/model access, so `OPENAI_API_KEY` matters for that workflow.
- `scripts/startup.py` stops processes on configured ports by default unless you pass `--no-kill`.
- Output is intentionally **HTML-first**, not Markdown.
- The web app depends on the migrated app DB; library mode does not persist to the app DB.

---

## Tech Stack

| Area | Technology |
|------|------------|
| Language | Python 3.11+ |
| API / services | FastAPI, Uvicorn |
| Agents / LLM | LangChain, LangChain-OpenAI, LangChain-Classic |
| App database | SQLite (`aiosqlite`) |
| Vector store | Chroma (`langchain-chroma`) |
| Config | JSON domain files + `.env` (`python-dotenv`) |
| Validation / models | Pydantic |
| Docker | Dockerfile + Docker Compose |
| CLI / scripts | Python scripts |

---

## License

MIT.
