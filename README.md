# Multi-Agent LangChain

A **lightweight Python package** for a config-driven multi-agent network: one **Orchestrator** plans and calls specialist **Agents**; you run two commands—**start** the network and **query** it.

---

## Two commands

| Command | What it does |
|--------|----------------|
| **`python scripts/startup.py`** | Starts the orchestrator + all agents (ports from config). Logs query, plan, and each agent call in the terminal. |
| **`python scripts/query_cli.py "Your question"`** | Sends a query, prints step-by-step agent iteration and final answer. Use `--trace` to see URLs and request/response bodies. |

One-time setup: create a Postgres DB, set `.env`, then run **`python scripts/migrate.py`** once.

---

## Quick start

```bash
# 1. Install
cd multi-agent-langchain
python3 -m venv venv && source venv/bin/activate
pip install -e .

# 2. Config
cp config/env/.env.example config/env/.env
# Set POSTGRES_APP_URL, OPENAI_API_KEY (and optionally CHROMA_PATH, POSTGRES_* for tools)

# 3. DB (once)
# Create a Postgres database, then:
PYTHONPATH=. python scripts/migrate.py

# 4. Run
# Terminal 1 – start network
PYTHONPATH=. python scripts/startup.py

# Terminal 2 – send a query
PYTHONPATH=. python scripts/query_cli.py "What are the safety guidelines for product X?"
```

You’ll see the query, plan, each `→ agent` / `← agent` line, and the final answer in the CLI and in the startup terminal logs.

---

## What’s in the box

- **Orchestrator** (FastAPI): receives a query → plans steps (LLM) → calls agents over HTTP → persists requests/plans/step_results in Postgres → synthesizes final answer.
- **Agents** (FastAPI, one process per agent): LangChain agents with system prompt, guardrails, and tools (e.g. `query_facts`, `search_docs`). Ports and config come from a domain JSON file.
- **Config**: one JSON per domain (orchestrator + agents + data_sources) and one `.env`. No code changes for new use cases—edit config only.

---

## Architecture (message flow)

Detailed flow of how a query becomes a final answer. Arrows show direction and content of each call.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  User / query_cli                                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  ①  POST /query  { "query": "What are the safety guidelines for product X?" }
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR  (port 8000)                                                        │
│  • Persist request (app.requests)                                                │
│  • Planner (LLM): build plan → [ { agent_name, task_description }, ... ]          │
│  • Persist plan (app.plans)                                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  ②  For each step in plan:
    │     POST http://127.0.0.1:{agent.port}/invoke
    │     { "task": "<task_description>", "context": "Original query: ...\nStep 1 (...): ..." }
    │
    ├──────────────────────────┬──────────────────────────┬──────────────────────────┐
    ▼                          ▼                          ▼                          │
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                      │
│  AGENT          │  │  AGENT          │  │  AGENT          │                      │
│  researcher     │  │  analyst        │  │  writer         │                      │
│  (port 8001)    │  │  (port 8002)    │  │  (port 8003)    │                      │
│                 │  │                 │  │                 │                      │
│  Tools:         │  │  Tools:         │  │  Tools:         │                      │
│  search_docs,   │  │  query_facts    │  │  (none)         │                      │
│  query_facts    │  │                 │  │                 │                      │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘                      │
    │    │                    │    │                │    │                          │
    │    │  (tools call       │    │                │    │                          │
    │    │   data layer)      │    │                │    │                          │
    ▼    ▼                    ▼    ▼                ▼    ▼                          │
┌─────────────────────────────────────────────────────────────────────────────┐   │
│  DATA LAYER                                                                  │   │
│  • Postgres (connected): query_facts → SELECT ...                            │   │
│  • Chroma: search_docs → vector search                                      │   │
└─────────────────────────────────────────────────────────────────────────────┘   │
    │                          │                          │                        │
    │  ③  HTTP 200             │  ③  HTTP 200             │  ③  HTTP 200          │
    │     { "result": "...",   │     { "result": "...",   │     { "result": "..."  │
    │       "status", "latency_ms" }  "status", "latency_ms" }  "status", ... }     │
    └──────────────────────────┴──────────────────────────┴────────────────────────┘
    │
    │  Orchestrator collects step results, persists (app.step_results)
    │  Reporter (LLM): synthesize final answer from query + step_results
    │  Persist final_answer, status (app.requests)
    │
    │  ④  Response to client: { "request_id", "status": "completed", "final_answer": "..." }
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  User / query_cli  →  prints final answer (and step-by-step if trace)          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Summary**

| Step | From → To | Message |
|------|-----------|---------|
| ① | User/CLI → Orchestrator | `POST /query` with `{ query }` |
| ② | Orchestrator → Agent (per step) | `POST /invoke` with `{ task, context }` (context = original query + prior step results) |
| ③ | Agent → Orchestrator | HTTP 200 with `{ result, status, latency_ms }` |
| ④ | Orchestrator → User/CLI | Response with `{ request_id, status, final_answer }` |

Agents run in separate processes (one per port). The orchestrator calls them over HTTP in the order of the plan; each agent may use its tools (Postgres, Chroma) before returning. The orchestrator then synthesizes the final answer from all step results and returns it to the client.

---

## Project layout

```
multi-agent-langchain/
├── config/domains/          # Domain JSON (e.g. manufacturing.json)
├── config/env/              # .env (secrets)
├── src/
│   ├── core/                # Config loader, contracts
│   ├── data_access/         # Postgres + Chroma clients
│   ├── tools/               # query_facts, search_docs
│   ├── agent/               # Agent FastAPI (POST /invoke)
│   ├── orchestrator/        # Planner, executor, reporter, FastAPI (POST /query)
│   └── gateway/             # Optional reverse proxy
├── migrations/versions/     # One SQL file: app.requests, app.plans, app.step_results
├── scripts/
│   ├── startup.py           # Start orchestrator + agents
│   ├── query_cli.py         # Send query, print steps + answer
│   └── migrate.py           # Run DB migration (once)
├── pyproject.toml
└── README.md
```

---

## Commands

| Command | Description |
|--------|--------------|
| `PYTHONPATH=. python scripts/migrate.py` | Run DB migration once (needs `POSTGRES_APP_URL`). |
| `PYTHONPATH=. python scripts/startup.py` | Start orchestrator + agents. `--no-kill`, `--background`, `--list-ports`, `--config <path>`. |
| `PYTHONPATH=. python scripts/query_cli.py "question"` | Send query; prints request_id, steps, final answer. |
| `PYTHONPATH=. python scripts/query_cli.py "question" --trace` | Same + full URL and request/response for each HTTP call. |

From project root; or use `pip install -e .` and omit `PYTHONPATH=.`.

---

## Configuration

- **Domain JSON** (`config/domains/<id>.json`): `domain_id`, `orchestrator` (name, port, system_prompt, guardrails, tool_names), `agents[]`, `data_sources[]`, `env_file_path`.
- **.env** (path in JSON): `POSTGRES_APP_URL` (required), `OPENAI_API_KEY` (required), `CHROMA_PATH`, `POSTGRES_*` for tools.

---

## API (for integration)

- **Orchestrator**: `POST /query` → `{ "query": "..." }` → `{ "request_id", "status", "final_answer", "error"? }`. `GET /health`.
- **Agent**: `POST /invoke` → `{ "task", "context"? }` → `{ "result", "status", "latency_ms" }`. `GET /health`.

---

## For developers

### 1. Extending to a new use case

To support a new domain (e.g. HR, support, internal docs):

1. **Add a domain config**  
   Create `config/domains/<domain_id>.json` (e.g. `hr.json`). Copy the structure from `config/domains/manufacturing.json`:
   - `domain_id`, `domain_name`, `env_file_path`
   - `orchestrator`: `name`, `port`, `system_prompt`, `guardrails`, `tool_names` (orchestrator usually has `tool_names: []`)
   - `agents`: list of agents; each has `name`, `port`, `system_prompt`, `guardrails`, `tool_names`
   - `data_sources`: list of `{ "id", "type", "engine", "connection_id" }`; for Chroma add `"collection_name"`
   - `session_store`: `{ "type": "postgres", "connection_id": "POSTGRES_APP_URL" }`

2. **Environment**  
   Use the same `.env` or a new one (e.g. `config/env/hr.env`) and set `env_file_path` in the JSON. Ensure `POSTGRES_APP_URL`, `OPENAI_API_KEY`, and any `connection_id` env vars used in `data_sources` are set.

3. **Run with that domain**  
   ```bash
   PYTHONPATH=. python scripts/startup.py --config config/domains/hr.json
   PYTHONPATH=. python scripts/query_cli.py "Your HR question"
   ```

No changes to orchestrator or agent **code**—only new config. If you need a new capability (e.g. call an external API, read from another DB), add a **new tool** (see below) and reference it in the right agents’ `tool_names`.

---

### 2. Defining new tools

Tools are LangChain tools that agents can call. The registry in `src/tools/registry.py` maps `tool_names` from config to actual tool instances, injecting data clients where needed.

**Step 1 – Implement the tool**

- Add a module under `src/tools/` (e.g. `src/tools/rel_db/query.py` or a new subpackage).
- Create a **factory function** that returns a LangChain tool (use `@tool` from `langchain_core.tools`). The factory can take a client (DB URL, retriever, etc.) so the registry can inject it.

Example (conceptually like `query_facts`):

```python
# src/tools/my_tool/thing.py
from langchain_core.tools import tool

def create_my_tool(some_client):  # client comes from build_clients()
    @tool
    def my_tool(arg: str) -> str:
        """Description for the LLM: what this tool does and when to use it."""
        # use some_client, return a string
        return "result"
    return my_tool
```

**Step 2 – Register the tool**

- In `src/tools/registry.py`, in `get_tools(tool_names, clients)`:
  - For each `name` in `tool_names`, if `name == "my_tool"`, get the right client from `clients` (keyed by `data_sources[].id`), call your factory, and append the result to `result`.

Example:

```python
elif name == "my_tool":
    client = clients.get("my_data_source_id")  # id from config data_sources
    if client is None:
        continue
    result.append(create_my_tool(client))
```

**Step 3 – Wire config**

- In your domain JSON, ensure the tool’s **data source** exists under `data_sources` (so `build_clients` fills `clients["my_data_source_id"]`).
- Add `"my_tool"` to the `tool_names` list of any agent that should use it.

Agents receive only the tools listed in their `tool_names`; the orchestrator does not run tools itself.

---

### 3. Adapting to a specific use case

To tailor the package to a concrete use case (e.g. “HR policy answers”, “support ticket summarization”):

1. **Define the roles**  
   Decide which agents you need (e.g. “researcher”, “analyst”, “writer”) and what each is responsible for. One agent per role is a good default.

2. **Define data sources**  
   In `data_sources`, list every DB or vector store the agents need:
   - **Postgres**: `{ "id": "hr_db", "type": "rel_db", "engine": "postgres", "connection_id": "POSTGRES_HR_URL" }`
   - **Chroma**: `{ "id": "docs", "type": "vector_db", "engine": "chroma", "connection_id": "CHROMA_PATH", "collection_name": "hr_policies" }`  
   Set the corresponding env vars in `.env`.

3. **Assign tools per agent**  
   In each agent’s `tool_names`, list only the tools that role should use (e.g. researcher: `["search_docs", "query_facts"]`; writer: `[]`). Use the same tool names you register in `src/tools/registry.py`.

4. **Write prompts and guardrails**  
   - **Orchestrator** `system_prompt`: instruct it to understand the query, plan steps, delegate to the right agents by name, and synthesize a final answer. Mention the list of agent names.  
   - **Each agent** `system_prompt`: role, responsibility, and “use only the provided tools”.  
   - **Guardrails**: short list of rules (e.g. “Do not fabricate data.”, “Max 500 words.”). These are passed to the agent runtime; keep them enforceable and clear.

5. **Optional: new tools**  
   If the use case needs a new capability (e.g. call an API, read from another system), add the tool in `src/tools/` and register it as in **Defining new tools** above, then add it to the right agents’ `tool_names`.

6. **Test**  
   Run `startup.py` with your domain config and send representative queries via `query_cli.py`. Use `--trace` to inspect requests and responses. Adjust prompts, guardrails, or tool assignments until behavior matches the use case.

---

## License

MIT.
