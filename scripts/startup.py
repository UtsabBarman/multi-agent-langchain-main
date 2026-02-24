#!/usr/bin/env python3
"""
Startup script: kill processes on app ports (from config), then start orchestrator + agents.
Optional: --no-kill, --background, --list-ports.
"""
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

for p in [ROOT / "config" / "env" / ".env", ROOT / ".env"]:
    if p.exists():
        load_dotenv(p)
        break

from src.core.config.loader import load_domain_config

PID_FILE = ROOT / "scripts" / ".startup_pids"

processes = []


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


def kill_port(port: int, dry_run: bool = False) -> bool:
    """Kill processes listening on port. Returns True if something was killed or dry_run."""
    pids = get_pids_on_port(port)
    if not pids:
        return True
    if dry_run:
        print(f"  Port {port}: would kill PIDs {pids}")
        return True
    for pid in pids:
        try:
            subprocess.run(["kill", "-9", str(pid)], check=True, timeout=5)
            print(f"  Killed PID {pid} on port {port}")
        except subprocess.CalledProcessError as e:
            print(f"  Warning: failed to kill PID {pid} on port {port}: {e}", file=sys.stderr)
            return False
    return True


def kill_ports(ports: list[int], dry_run: bool = False) -> None:
    """Kill processes on all given ports. Slight delay after so ports are released."""
    for port in sorted(ports, reverse=True):
        kill_port(port, dry_run=dry_run)
    if not dry_run and ports:
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


def cleanup(sig=None, frame=None):
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Kill processes on app ports, then start orchestrator + agents.")
    parser.add_argument("--config", default=os.environ.get("CONFIG_PATH", "config/domains/manufacturing.json"), help="Domain config path")
    parser.add_argument("--no-kill", action="store_true", help="Do not kill processes on ports; only start")
    parser.add_argument("--background", action="store_true", help="Run in background; write PIDs to scripts/.startup_pids")
    parser.add_argument("--list-ports", action="store_true", help="Only list ports from config and which are in use; no kill, no start")
    args = parser.parse_args()

    config_path = args.config
    if not (ROOT / config_path).exists():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_domain_config(config_path, project_root=ROOT)
    ports = [config.orchestrator.port] + [a.port for a in config.agents]

    if args.list_ports:
        print("Ports from config:", sorted(ports))
        for port in sorted(ports):
            pids = get_pids_on_port(port)
            status = f"in use (PIDs {pids})" if pids else "free"
            print(f"  {port}: {status}")
        return

    if not args.no_kill:
        print("Freeing ports...")
        kill_ports(ports)

    env = {**os.environ, "CONFIG_PATH": config_path}

    # Start orchestrator
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.orchestrator.main"],
        cwd=str(ROOT),
        env={**env, "PORT": str(config.orchestrator.port)},
        stdout=subprocess.DEVNULL if args.background else None,
        stderr=subprocess.PIPE if args.background else None,
    )
    processes.append(proc)
    print(f"Orchestrator started on port {config.orchestrator.port} (PID {proc.pid})")

    if not wait_for_health(f"http://127.0.0.1:{config.orchestrator.port}"):
        time.sleep(2)

    # Start agents
    for agent in config.agents:
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.agent.main", "--agent-id", agent.name, "--config-path", config_path],
            cwd=str(ROOT),
            env={**env, "AGENT_ID": agent.name},
            stdout=subprocess.DEVNULL if args.background else None,
            stderr=subprocess.PIPE if args.background else None,
        )
        processes.append(proc)
        print(f"Agent {agent.name} started on port {agent.port} (PID {proc.pid})")
        time.sleep(1)

    if args.background:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("\n".join(str(p.pid) for p in processes))
        print(f"All running in background. PIDs saved to {PID_FILE}")
        return

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    print("All running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
        for p in processes:
            if p.poll() is not None:
                print(f"Process {p.pid} exited.")
                cleanup()


if __name__ == "__main__":
    main()
