"""
Mortgage application review example: define mortgage agents in code, start services,
then run a sample application-review query.

Run from project root (after: pip install -e . and once: python scripts/migrate.py):

  python examples/mortgage_agents.py

This script:
  1. Builds a mortgage domain config in code
  2. Writes config to a temp file so subprocesses can load it
  3. Frees ports and starts the orchestrator and all mortgage agents
  4. Runs one sample mortgage application review query and prints the result
  5. Keeps the app running; open the UI in your browser. Press Ctrl+C to stop.

Notes:
  - The Application Parser uses parse_mortgage_pdf against a local PDF path.
  - The Rule Validator uses validate_mortgage_rules against asn_mortgage_rules.json.
  - The Reporter uses create_mortgage_report to write a downloadable HTML report.
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


def build_mortgage_domain_config() -> DomainConfig:
    """Define the mortgage domain: orchestrator, agents, tools, and data sources."""
    orchestrator = AgentConfig(
        name="orchestrator",
        label="Mortgage Orchestrator",
        port=8100,
        system_prompt=(
            "You are the Mortgage Orchestrator. For every mortgage application review, "
            "delegate in this exact order: application_parser, rule_validator, reporter. "
            "The application_parser parses the supplied PDF path and extracts structured "
            "application JSON. The rule_validator checks that JSON against the supplied "
            "ASN mortgage rules JSON file. The reporter creates a downloadable HTML "
            "report and returns its link. Use only available agents. "
            "Format output as clean HTML (<p>, <h2>, <ul>, <li>, <strong>, <pre>)."
        ),
        guardrails=[
            "Do not skip parser, validator, or reporter steps.",
            "Do not approve an application unless the validator explicitly says it passes.",
            "Return a structured final answer with clear rule violations.",
        ],
        tool_names=[],
    )

    application_parser = AgentConfig(
        name="application_parser",
        label="Application Parser",
        port=8101,
        system_prompt=(
            "You are the Application Parser. Use the parse_mortgage_pdf tool with the "
            "PDF path from the task/context. Return the exact parsed application JSON "
            "from the tool in a clean HTML <pre> block. Do not summarize away fields."
        ),
        guardrails=[
            "Do not invent missing applicant data.",
            "Preserve numeric values and units from the source.",
            "Flag ambiguous or unreadable fields in missing_fields.",
        ],
        tool_names=["parse_mortgage_pdf"],
    )

    rule_validator = AgentConfig(
        name="rule_validator",
        label="Rule Validator",
        port=8102,
        system_prompt=(
            "You are the Rule Validator. Use validate_mortgage_rules with the parsed "
            "application JSON from the application_parser step and the rules JSON path "
            "from the original query. Return the validator JSON in a clean HTML <pre> "
            "block, emphasizing failed rules, warnings, unknown checks, evidence, and "
            "why each rule was not followed."
        ),
        guardrails=[
            "Do not fabricate internal rule IDs or thresholds.",
            "If internal rules are unavailable, mark affected checks as unknown.",
            "Separate failed rules from warnings and missing information.",
        ],
        tool_names=["validate_mortgage_rules"],
    )

    reporter = AgentConfig(
        name="reporter",
        label="Reporter",
        port=8103,
        system_prompt=(
            "You are the Mortgage Report Writer. Use create_mortgage_report with the "
            "validator JSON from the rule_validator step. Then write a concise final "
            "message containing the application summary, decision recommendation, failed "
            "rules, warnings, missing data/manual-review items, and the download link "
            "returned by the tool."
        ),
        guardrails=[
            "Stick to the parser and validator evidence.",
            "Do not hide failed or unknown rule checks.",
            "Make the final recommendation conditional when required data is missing.",
        ],
        tool_names=["create_mortgage_report"],
    )

    data_sources = [
        DataSourceConfig(
            id="app_db",
            type="rel_db",
            engine="sqlite",
            connection_id="SQLITE_APP_PATH",
        )
    ]

    session_store = SessionStoreConfig(
        type="sqlite",
        connection_id="SQLITE_APP_PATH",
    )

    return DomainConfig(
        domain_id="mortgage_review",
        domain_name="Mortgage Application Review",
        env_file_path="config/env/.env",
        orchestrator=orchestrator,
        agents=[application_parser, rule_validator, reporter],
        data_sources=data_sources,
        session_store=session_store,
    )


def sample_mortgage_query() -> str:
    """Sample query that points agents at local sample data files."""
    pdf_path = ROOT / "examples" / "sample_data" / "asn_mortgage_submission_pack.pdf"
    rules_path = ROOT / "examples" / "sample_data" / "asn_mortgage_rules.json"
    return f"""
Review this ASN mortgage application and produce a structured report showing which
rules are not followed and why.

PDF path: {pdf_path}
Rules JSON path: {rules_path}

Workflow requirements:
1. Application Parser must parse the PDF and extract detailed application information as JSON.
2. Rule Validator must validate the extracted JSON against the rules JSON.
3. Reporter must create a nice HTML report document and return the local download link.
"""


def main() -> None:
    global _temp_config_path

    config = build_mortgage_domain_config()

    # Write config to a temp file so orchestrator and agent subprocesses can load it
    fd, _temp_config_path = tempfile.mkstemp(suffix=".json", prefix="mortgage_agent_config_")
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

    print("Starting mortgage orchestrator and agents...")
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
        print(f"  Agent {agent.get_display_label()} on port {agent.port} (PID {proc.pid})")
        time.sleep(1)

    orch_port = config.orchestrator.port
    print()
    print("App is running. Mortgage Orchestrator UI: http://127.0.0.1:{}/".format(orch_port))
    print()

    query = sample_mortgage_query()
    print("Running sample mortgage application review query...")
    result = run_query_with_config(config, query, env=env)
    print("Request ID:", result.request_id)
    print("Status:", result.status)
    if result.error:
        print("Error:", result.error)
    if result.final_answer:
        excerpt = (
            result.final_answer[:800] + "..."
            if len(result.final_answer) > 800
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
