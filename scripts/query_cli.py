#!/usr/bin/env python3
"""Send a query to the orchestrator from the command line. Prints query, agent iteration (steps), and final answer."""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_BASE_URL", "http://127.0.0.1:8000")


def _trunc(s: str, max_len: int = 100) -> str:
    s = str(s)
    return (s[:max_len] + "…") if len(s) > max_len else s


def _trace_request(method: str, url: str, body: dict | None, trace: bool) -> None:
    if not trace:
        return
    print(f"[REQUEST] {method} {url}", flush=True)
    if body is not None:
        print("[REQUEST BODY]", flush=True)
        print(json.dumps(body, indent=2), flush=True)
    print(flush=True)


def _trace_response(status: int, headers: dict, body: Any, trace: bool, max_body_len: int = 2000) -> None:
    if not trace:
        return
    print(f"[RESPONSE] {status}", flush=True)
    if headers:
        for k, v in list(headers.items())[:10]:
            print(f"  {k}: {v}", flush=True)
    if body is not None:
        print("[RESPONSE BODY]", flush=True)
        try:
            raw = json.dumps(body, indent=2) if isinstance(body, dict) else str(body)
            if len(raw) > max_body_len:
                raw = raw[:max_body_len] + "\n… (truncated)"
            print(raw, flush=True)
        except Exception:
            print(str(body)[:max_body_len], flush=True)
    print("---", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Send a query to the orchestrator. Prints query, step-by-step agent calls, and final answer.")
    parser.add_argument("query", nargs="*", help="Query text (or pass as single argument)")
    parser.add_argument("--url", default=ORCHESTRATOR_URL, help="Orchestrator base URL")
    parser.add_argument("--trace", action="store_true", help="Print each URL, request body, and response (status + body) so you can see what’s going on")
    args = parser.parse_args()
    query = " ".join(args.query).strip()
    if not query:
        print("Usage: PYTHONPATH=. python scripts/query_cli.py \"Your question here\"", file=sys.stderr)
        sys.exit(1)

    base = args.url.rstrip("/")
    trace = args.trace
    try:
        print("Query:", query, flush=True)
        print("---", flush=True)

        # POST /query
        post_url = f"{base}/query"
        post_body = {"query": query}
        _trace_request("POST", post_url, post_body, trace)
        r = httpx.post(post_url, json=post_body, timeout=120)
        try:
            resp_body = r.json()
        except Exception:
            resp_body = r.text
        _trace_response(r.status_code, dict(r.headers), resp_body, trace)
        r.raise_for_status()
        data = resp_body if isinstance(resp_body, dict) else {}
        request_id = data.get("request_id")
        print("Request ID:", request_id, flush=True)
        print("Status:", data.get("status"), flush=True)

        # GET /request/{id}
        if request_id:
            try:
                get_url = f"{base}/request/{request_id}"
                _trace_request("GET", get_url, None, trace)
                tr = httpx.get(get_url, timeout=10)
                try:
                    tr_body = tr.json()
                except Exception:
                    tr_body = tr.text
                _trace_response(tr.status_code, dict(tr.headers), tr_body, trace)
                if tr.status_code == 200:
                    trace_data = tr_body if isinstance(tr_body, dict) else {}
                    steps = (trace_data.get("plan") or {}).get("steps") or []
                    step_results = trace_data.get("step_results") or []
                    by_idx = {sr["step_index"]: sr for sr in step_results}
                    for step in steps:
                        si = step.get("step_index", 0)
                        agent = step.get("agent_name", "?")
                        task = _trunc(step.get("task_description", ""), 100)
                        print(f"  [step {si}] → {agent}: {task}", flush=True)
                        sr = by_idx.get(si)
                        if sr:
                            out = sr.get("output_payload") or sr.get("result") or ""
                            if isinstance(out, dict):
                                out = out.get("text", str(out))
                            out_str = _trunc(str(out), 150)
                            lat = sr.get("latency_ms")
                            lat_str = f" ({lat} ms)" if lat is not None else ""
                            print(f"  [step {si}] ← {agent}: {out_str}{lat_str}", flush=True)
                        else:
                            print(f"  [step {si}] ← {agent}: (no result)", flush=True)
                    print("---", flush=True)
            except Exception:
                pass  # ignore trace fetch errors

        if data.get("final_answer"):
            print("Final answer:", flush=True)
            print(data["final_answer"], flush=True)
        if data.get("error"):
            print("Error:", data["error"], file=sys.stderr)
    except httpx.ConnectError as e:
        print(f"Cannot reach orchestrator at {args.url}. Is it running?", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
