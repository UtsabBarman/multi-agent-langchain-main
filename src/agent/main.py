"""FastAPI app for a single agent. Run with: python -m src.agent.main --agent-id researcher --config-path config/domains/manufacturing.json"""
from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

from src.core.config.loader import load_domain_config
from src.core.contracts.agent import AgentInvokeRequest, AgentInvokeResponse
from src.agent.deps import get_agent_config, get_clients, get_agent_runner

app = FastAPI(title="Multi-Agent: Agent API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Set at startup
DOMAIN_CONFIG = None
AGENT_RUNNER = None
AGENT_NAME = None


@app.on_event("startup")
def startup():
    global DOMAIN_CONFIG, AGENT_RUNNER, AGENT_NAME
    config_path = os.environ.get("CONFIG_PATH", "config/domains/manufacturing.json")
    agent_id = os.environ.get("AGENT_ID", "researcher")
    root = Path(__file__).resolve().parent.parent.parent
    DOMAIN_CONFIG = load_domain_config(config_path, project_root=root)
    agent_config = get_agent_config(DOMAIN_CONFIG, agent_id)
    clients = get_clients(DOMAIN_CONFIG, root)
    AGENT_RUNNER = get_agent_runner(agent_config, clients)
    AGENT_NAME = agent_id


@app.get("/health")
def health():
    return {"status": "ok", "agent": AGENT_NAME}


@app.post("/invoke", response_model=AgentInvokeResponse)
def invoke(req: AgentInvokeRequest):
    if AGENT_RUNNER is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    log = logging.getLogger(f"agent.{AGENT_NAME}")
    task = req.task
    task_preview = (task[:120] + "…") if len(task) > 120 else task
    log.info("RECV: %s", task_preview)
    context = req.context
    if isinstance(context, dict):
        context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
    else:
        context_str = str(context)
    input_text = f"{task}\n\nContext:\n{context_str}" if context_str else task
    start = time.perf_counter()
    try:
        result = AGENT_RUNNER(input_text)
        latency_ms = int((time.perf_counter() - start) * 1000)
        out_preview = (str(result)[:120] + "…") if len(str(result)) > 120 else str(result)
        log.info("SEND: %s (%s ms)", out_preview, latency_ms)
        return AgentInvokeResponse(result=result, status="success", latency_ms=latency_ms)
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        log.warning("SEND (failed): %s (%s ms)", e, latency_ms)
        return AgentInvokeResponse(result=str(e), status="failed", latency_ms=latency_ms)


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-id", default="researcher")
    parser.add_argument("--config-path", default="config/domains/manufacturing.json")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    os.environ["AGENT_ID"] = args.agent_id
    os.environ["CONFIG_PATH"] = args.config_path
    root = Path(__file__).resolve().parent.parent.parent
    _cfg = load_domain_config(args.config_path, project_root=root)
    _agent = _cfg.get_agent_by_name(args.agent_id)
    port = args.port or (_agent.port if _agent else 8001)
    uvicorn.run(app, host="0.0.0.0", port=port)
