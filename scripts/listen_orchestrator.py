#!/usr/bin/env python3
"""
Listen to the orchestrator at localhost:8000 continuously and print.
Polls GET /trace/last every N seconds and prints the latest request (query, plan, steps, final answer).
Run from project root: PYTHONPATH=. python scripts/listen_orchestrator.py
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

DEFAULT_URL = "http://127.0.0.1:8000"
DEFAULT_INTERVAL = 5


def _trunc(s: str, max_len: int = 120) -> str:
    s = str(s)
    return (s[:max_len] + "…") if len(s) > max_len else s


def fetch_trace(base_url: str) -> dict | None:
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/trace/last", timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[error] {e}", flush=True)
    return None


def print_trace(data: dict) -> None:
    rid = data.get("request_id", "")[:12]
    query = data.get("query", "")
    status = data.get("status", "")
    print(f"\n{'='*60}")
    print(f"Request: {rid}…  |  Status: {status}")
    print(f"Query: {_trunc(query, 80)}")
    plan = data.get("plan") or {}
    steps = plan.get("steps") or []
    if steps:
        print("Plan:")
        for s in steps:
            print(f"  Step {s.get('step_index')} → {s.get('agent_name')}: {_trunc(s.get('task_description', ''), 60)}")
    step_results = data.get("step_results") or []
    if step_results:
        print("Step results:")
        for sr in step_results:
            out = sr.get("output_payload")
            if isinstance(out, dict) and "text" in out:
                out = out["text"]
            out_str = _trunc(str(out), 80)
            print(f"  Step {sr.get('step_index')} {sr.get('agent_name')}: {sr.get('status')} ({sr.get('latency_ms') or 0} ms) → {out_str}")
    final = data.get("final_answer") or ""
    if final:
        print("Final answer:")
        print(_trunc(final, 400))
    if data.get("error_message"):
        print("Error:", data.get("error_message"))
    print(f"{'='*60}\n", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Listen to orchestrator and print latest trace continuously.")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Orchestrator base URL (default: {DEFAULT_URL})")
    parser.add_argument("--interval", "-i", type=float, default=DEFAULT_INTERVAL, help="Poll interval in seconds (default: 5)")
    args = parser.parse_args()

    print(f"Listening to {args.url} every {args.interval}s (Ctrl+C to stop)", flush=True)
    last_rid: str | None = None

    while True:
        try:
            data = fetch_trace(args.url)
            if data:
                rid = data.get("request_id")
                if rid != last_rid or data.get("status") == "running":
                    print_trace(data)
                    last_rid = rid
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.", flush=True)
            break


if __name__ == "__main__":
    main()
