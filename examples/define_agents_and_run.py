"""
Single script to run the app: define agents and tools in code, start orchestrator + agents, then run a query.

Run from project root (after: pip install -e . and once: python scripts/migrate.py):

  python examples/define_agents_and_run.py

This script:
  1. Builds domain config in code (orchestrator + agents + tools + data sources)
  2. Writes config to a temp file so subprocesses can load it
  3. Frees ports and starts the orchestrator and all agents
  4. Runs one example query and prints the result
  5. Keeps the app running; open the UI in your browser. Press Ctrl+C to stop.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Project root (parent of examples/)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config.env import ensure_project_env
from src.core.config.models import (
    AgentConfig,
    DataSourceConfig,
    DomainConfig,
    SessionStoreConfig,
)
from src.run import run_query_with_config

ensure_project_env(ROOT)

# Subprocess handles and temp config path for cleanup
processes: list[subprocess.Popen[bytes]] = []
_temp_config_path: str | None = None


def get_pids_on_port(port: int) -> list[int]:
    """Return list of PIDs listening on the given port (macOS/Linux)."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        out = (result.stdout or "").strip()
        if result.returncode != 0 or not out:
            return []
        return [int(x) for x in out.split() if x.strip().isdigit()]
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        return []


def kill_port(port: int) -> bool:
    """Kill processes listening on port."""
    pids = get_pids_on_port(port)
    for pid in pids:
        try:
            subprocess.run(["kill", "-TERM", str(pid)], check=True, timeout=5)
            time.sleep(0.5)
            still_running = (
                subprocess.run(
                    ["kill", "-0", str(pid)],
                    cwd=str(ROOT),
                    capture_output=True,
                    timeout=3,
                ).returncode
                == 0
            )
            if still_running:
                subprocess.run(["kill", "-KILL", str(pid)], check=True, timeout=5)
        except subprocess.CalledProcessError:
            pass
    return True


def kill_ports(ports: list[int]) -> None:
    for port in sorted(ports, reverse=True):
        kill_port(port)
    if ports:
        time.sleep(2)


def wait_for_health(url: str, timeout: int = 30) -> bool:
    try:
        import httpx

        start = time.time()
        while time.time() - start < timeout:
            try:
                r = httpx.get(f"{url}/health", timeout=2)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
    except ImportError:
        pass
    return False


def cleanup(sig=None, frame=None) -> None:
    global _temp_config_path
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    if _temp_config_path and os.path.isfile(_temp_config_path):
        try:
            os.unlink(_temp_config_path)
        except Exception:
            pass
    sys.exit(0)


def build_my_domain_config() -> DomainConfig:
    """Define the domain: orchestrator, agents, tools (by name), and data sources."""
    orchestrator = AgentConfig(
        name="orchestrator",
        port=8000,
        system_prompt=(
            "You are the Orchestrator. Plan steps, delegate to the right agents, "
            "and synthesize the final answer. Use only the available agents. "
            "Format output as clean HTML (<p>, <h2>, <ul>, <li>, <strong>)."
        ),
        guardrails=["Do not skip steps.", "Return a clear final answer."],
        tool_names=[],
    )

    researcher = AgentConfig(
        name="researcher",
        port=8001,
        system_prompt=(
            "You are the Research agent. Use only the provided tools: "
            "search_docs, query_facts, index_doc. Format responses as clean HTML."
        ),
        guardrails=["Do not fabricate data.", "Cite only from tool results."],
        tool_names=["search_docs", "query_facts", "index_doc", "request_user_validation"],
    )

    analyst = AgentConfig(
        name="analyst",
        port=8002,
        system_prompt="You are the Analyst. Synthesize and compare. Format as clean HTML.",
        guardrails=["Max 500 words per response."],
        tool_names=["query_facts"],
    )

    writer = AgentConfig(
        name="writer",
        port=8003,
        system_prompt="You write clear reports from the given context. Format as clean HTML.",
        guardrails=["Stick to the provided context."],
        tool_names=[],
    )

    data_sources = [
        DataSourceConfig(
            id="app_db",
            type="rel_db",
            engine="sqlite",
            connection_id="SQLITE_APP_PATH",
        ),
        DataSourceConfig(
            id="facts_db",
            type="rel_db",
            engine="sqlite",
            connection_id="SQLITE_MANUFACTURING_PATH",
        ),
        DataSourceConfig(
            id="docs",
            type="vector_db",
            engine="chroma",
            connection_id="CHROMA_PATH",
            collection_name="manufacturing_docs",
        ),
    ]

    session_store = SessionStoreConfig(
        type="sqlite",
        connection_id="SQLITE_APP_PATH",
    )

    return DomainConfig(
        domain_id="my_domain",
        domain_name="My Multi-Agent Domain",
        env_file_path="config/env/.env",
        orchestrator=orchestrator,
        agents=[researcher, analyst, writer],
        data_sources=data_sources,
        session_store=session_store,
    )


def main() -> None:
    global _temp_config_path

    config = build_my_domain_config()

    # Write config to a temp file so orchestrator and agent subprocesses can load it
    fd, _temp_config_path = tempfile.mkstemp(suffix=".json", prefix="multi_agent_config_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2)
    except Exception:
        os.close(fd)
        os.unlink(_temp_config_path)
        raise

    config_path = _temp_config_path
    env = {**os.environ, "CONFIG_PATH": config_path}
    ports = [config.orchestrator.port] + [a.port for a in config.agents]

    print("Freeing ports...")
    kill_ports(ports)

    print("Starting orchestrator and agents...")
    # Orchestrator
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.orchestrator.main"],
        cwd=str(ROOT),
        env={**env, "PORT": str(config.orchestrator.port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    processes.append(proc)
    print(f"  Orchestrator on port {config.orchestrator.port} (PID {proc.pid})")

    if not wait_for_health(f"http://127.0.0.1:{config.orchestrator.port}"):
        time.sleep(2)

    for agent in config.agents:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "src.agent.main",
                "--agent-id",
                agent.name,
                "--config-path",
                config_path,
            ],
            cwd=str(ROOT),
            env={**env, "AGENT_ID": agent.name},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(proc)
        print(f"  Agent {agent.name} on port {agent.port} (PID {proc.pid})")
        time.sleep(1)

    orch_port = config.orchestrator.port
    print()
    print("App is running. Orchestrator UI: http://127.0.0.1:{}/".format(orch_port))
    print()

    # Run one example query
    query = "What are the safety guidelines for Product X?"
    print("Running example query:", repr(query))
    result = run_query_with_config(config, query, env=env)
    print("Request ID:", result.request_id)
    print("Status:", result.status)
    if result.error:
        print("Error:", result.error)
    if result.final_answer:
        excerpt = (
            result.final_answer[:500] + "..."
            if len(result.final_answer) > 500
            else result.final_answer
        )
        print("Final answer (excerpt):", excerpt)
    for step in result.step_results:
        print(f"  Step S{step.step_index} ({step.agent_name}): {step.status}")
    print()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    print("Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
        for p in processes:
            if p.poll() is not None:
                print(f"Process {p.pid} exited.")
                cleanup()


if __name__ == "__main__":
    main()
