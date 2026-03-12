"""FastAPI app for a single agent. Run with: python -m src.agent.main --agent-id researcher --config-path config/domains/manufacturing.json"""
from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

from src.core.logging_config import configure_log_format

configure_log_format()

from src.agent.deps import get_agent_config, get_agent_runner, get_clients
from src.core.config.loader import load_domain_config
from src.core.config.models import AgentConfig
from src.core.contracts.agent import AgentInvokeRequest, AgentInvokeResponse
from src.core.contracts.protocol import artifacts_from_content_and_steps, tool_calls_from_steps

app = FastAPI(title="Multi-Agent: Agent API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Set at startup
DOMAIN_CONFIG: Any = None
AGENT_RUNNER: Any = None
AGENT_NAME: str | None = None
AGENT_CONFIG: AgentConfig | None = None  # AgentConfig for UI label/icon from config

# Last invoke (for simple chat UI in iframe)
LAST_INVOKE: dict | None = None


def _avatar_cls(name: str) -> str:
    """CSS class for avatar color; matches orchestrator."""
    return name if name in ("researcher", "analyst", "writer") else "unknown"


@app.on_event("startup")
def startup():
    global DOMAIN_CONFIG, AGENT_RUNNER, AGENT_NAME, AGENT_CONFIG
    config_path = os.environ.get("CONFIG_PATH", "config/domains/manufacturing.json")
    agent_id = os.environ.get("AGENT_ID", "researcher")
    root = Path(__file__).resolve().parent.parent.parent
    DOMAIN_CONFIG = load_domain_config(config_path, project_root=root)
    agent_config = get_agent_config(DOMAIN_CONFIG, agent_id)
    clients = get_clients(DOMAIN_CONFIG, root)
    AGENT_RUNNER = get_agent_runner(agent_config, clients)
    AGENT_NAME = agent_id
    AGENT_CONFIG = agent_config


@app.get("/health")
def health():
    return {"status": "ok", "agent": AGENT_NAME}


@app.post("/invoke", response_model=AgentInvokeResponse)
def invoke(req: AgentInvokeRequest):
    global LAST_INVOKE
    if AGENT_RUNNER is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    log = logging.getLogger(f"agent.{AGENT_NAME}")
    run_id = getattr(req, "run_id", None) or getattr(req, "request_id", None) or ""
    step_id = getattr(req, "step_id", None) or ""
    task = req.task
    task_preview = (task[:120] + "…") if len(task) > 120 else task
    _log_extra = {"run_id": run_id, "agent": AGENT_NAME, "step_id": step_id}
    log.info("RECV: %s", task_preview, extra={**_log_extra, "event_type": "invoke_start"})
    context = req.context
    if isinstance(context, dict):
        context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
    else:
        context_str = str(context)
    input_text = f"{task}\n\nContext:\n{context_str}" if context_str else task
    start = time.perf_counter()
    try:
        result, steps, validation_payload = AGENT_RUNNER(input_text)
        latency_ms = int((time.perf_counter() - start) * 1000)
        content_str = result if isinstance(result, str) else str(result)
        artifacts = artifacts_from_content_and_steps(content_str, steps or [])
        tool_calls = tool_calls_from_steps(steps or [])
        art_dict = artifacts.model_dump()
        tc_dict = [t.model_dump() for t in tool_calls]
        log.info("status=success latency_ms=%s", latency_ms, extra={**_log_extra, "event_type": "invoke_finish"})
        if validation_payload:
            log.info("requires_validation: %s", validation_payload.get("message", "")[:80], extra={**_log_extra, "event_type": "requires_validation"})
            LAST_INVOKE = {"task": task, "result": result, "status": "requires_validation", "latency_ms": latency_ms, "steps": steps or [], "requires_validation": True, "validation_payload": validation_payload, "artifacts": art_dict}
            return AgentInvokeResponse(result=result, status="requires_validation", latency_ms=latency_ms, steps=steps, requires_validation=True, validation_payload=validation_payload, artifacts=art_dict, tool_calls=tc_dict)
        LAST_INVOKE = {"task": task, "result": result, "status": "success", "latency_ms": latency_ms, "steps": steps or [], "artifacts": art_dict}
        return AgentInvokeResponse(result=result, status="success", latency_ms=latency_ms, steps=steps, artifacts=art_dict, tool_calls=tc_dict)
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        log.warning("status=failed error=%s latency_ms=%s", str(e), latency_ms, extra={**_log_extra, "event_type": "invoke_finish"})
        err_list = [{"type": "error", "message": str(e), "retryable": False}]
        LAST_INVOKE = {"task": task, "result": str(e), "status": "failed", "latency_ms": latency_ms, "steps": [], "errors": err_list}
        return AgentInvokeResponse(result=str(e), status="failed", latency_ms=latency_ms, steps=None, errors=err_list)


@app.get("/last")
def get_last():
    """Return last invoke for the agent chat iframe UI."""
    return LAST_INVOKE or {}


def _agent_ui_html() -> str:
    # Label and icon from config (optional label, else derived from name)
    display_name: str
    letter: str
    avatar_cls: str
    if AGENT_CONFIG:
        display_name = AGENT_CONFIG.get_display_label()
        letter = AGENT_CONFIG.get_icon_letter()
        avatar_cls = _avatar_cls(AGENT_CONFIG.name)
    else:
        display_name = (AGENT_NAME or "agent").replace("_", " ").title()
        letter = display_name[0:1].upper() if display_name else "?"
        avatar_cls = _avatar_cls((AGENT_NAME or "").lower())
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>""" + display_name + """</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, sans-serif; background: #2d2d30; color: #e4e4e7; padding: 0.75rem; font-size: 0.9rem; }
    .avatar { width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 600; }
    .avatar.o { background: #8e8ea0; color: #fff; }
    .avatar.researcher { background: #0d9488; color: #fff; }
    .avatar.analyst { background: #6366f1; color: #fff; }
    .avatar.writer { background: #d97706; color: #fff; }
    .avatar.unknown { background: #52525b; color: #fff; }
    .meta { font-size: 0.7rem; color: #8e8ea0; margin-top: 0.2rem; }
    .empty { color: #8e8ea0; font-style: italic; }
    .msg-card { margin-top: 0.5rem; border-radius: 10px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); background: rgba(0,0,0,0.15); }
    .msg-card .msg-label { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.65rem; font-size: 0.7rem; font-weight: 600; color: #a0a0b0; text-transform: uppercase; letter-spacing: 0.03em; border-bottom: 1px solid rgba(255,255,255,0.06); }
    .msg-card details { border: none; }
    .msg-card details summary { cursor: pointer; font-size: 0.8rem; color: #19c37d; list-style: none; padding: 0.35rem 0.65rem; display: flex; align-items: center; gap: 0.35rem; }
    .msg-card details summary::-webkit-details-marker { display: none; }
    .msg-card details summary::before { content: "▶"; font-size: 0.6rem; transition: transform 0.15s; }
    .msg-card details[open] summary::before { transform: rotate(90deg); }
    .msg-card .msg-content { padding: 0.5rem 0.65rem 0.65rem; font-size: 0.85rem; line-height: 1.5; word-break: break-word; color: #e4e4e7; }
    .msg-card .msg-content p { margin: 0 0 0.5rem; }
    .msg-card .msg-content h2, .msg-card .msg-content h3 { margin: 0.5rem 0 0.25rem; font-weight: 600; }
    .msg-card .msg-content ul, .msg-card .msg-content ol { margin: 0.35rem 0; padding-left: 1.25rem; }
    .msg-card .msg-content a { color: #19c37d; }
    .msg-card.task .msg-label { color: #8e8ea0; }
    .msg-card.task details summary { color: #8e8ea0; }
    /* Thought / tool-call panel */
    .thought-panel {
      margin-top: 0.6rem;
      border-radius: 10px;
      background: linear-gradient(145deg, rgba(25,195,125,0.06) 0%, rgba(0,0,0,0.2) 100%);
      border: 1px solid rgba(25,195,125,0.2);
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.15);
    }
    .thought-panel summary {
      padding: 0.5rem 0.75rem;
      font-size: 0.8rem;
      color: #9ca3af;
      cursor: pointer;
      list-style: none;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      user-select: none;
      transition: color 0.15s, background 0.15s;
    }
    .thought-panel summary:hover { color: #19c37d; background: rgba(25,195,125,0.06); }
    .thought-panel summary::-webkit-details-marker { display: none; }
    .thought-panel summary .thought-icon { flex-shrink: 0; opacity: 0.9; }
    .thought-panel .thought-steps {
      padding: 0.5rem 0.75rem 0.75rem;
      border-top: 1px solid rgba(255,255,255,0.06);
    }
    .thought-step {
      display: flex;
      gap: 0.5rem;
      align-items: flex-start;
      padding: 0.5rem 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      font-size: 0.8rem;
    }
    .thought-step:last-child { border-bottom: none; }
    .thought-step .step-icon { flex-shrink: 0; margin-top: 0.15rem; }
    .thought-step .step-body { flex: 1; min-width: 0; }
    .thought-step .step-name { font-weight: 600; color: #19c37d; }
    .thought-step .step-in, .thought-step .step-out {
      margin-top: 0.25rem; font-size: 0.75rem; color: #9ca3af;
      white-space: pre-wrap; word-break: break-word;
      font-family: ui-monospace, monospace;
    }
    .thought-step.tool-end .step-out { color: #a7f3d0; }
    .thought-step.tool-error .step-out { color: #f87171; }
    .thought-step.tool-error .step-name { color: #f87171; }
  </style>
</head>
<body>
  <div id="chat"></div>
  <script>
    function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
    function sanitizeHtml(htmlStr) {
      if (!htmlStr || typeof htmlStr !== 'string') return '';
      var allowed = ['p','div','span','br','strong','b','em','i','u','h1','h2','h3','h4','ul','ol','li','a','blockquote','hr'];
      var wrap = document.createElement('div');
      wrap.innerHTML = htmlStr;
      function go(node) {
        if (node.nodeType === 3) return node.cloneNode(true);
        if (node.nodeType !== 1) return null;
        var tag = node.tagName.toLowerCase();
        if (allowed.indexOf(tag) === -1) {
          var f = document.createDocumentFragment();
          for (var i = 0; i < node.childNodes.length; i++) { var c = go(node.childNodes[i]); if (c) f.appendChild(c); }
          return f;
        }
        var out = document.createElement(tag);
        if (tag === 'a' && node.getAttribute('href')) {
          var href = (node.getAttribute('href') || '').trim();
          if (href.indexOf('javascript:') !== 0 && href.indexOf('data:') !== 0) out.setAttribute('href', href);
        }
        for (var i = 0; i < node.childNodes.length; i++) { var c = go(node.childNodes[i]); if (c) out.appendChild(c); }
        return out;
      }
      var safe = document.createElement('div');
      for (var i = 0; i < wrap.childNodes.length; i++) { var c = go(wrap.childNodes[i]); if (c) safe.appendChild(c); }
      return safe.innerHTML;
    }
    var agentLetter = """ + repr(letter) + """;
    var agentCls = """ + repr(avatar_cls) + """;
    var agentLabel = """ + repr(display_name) + """;
    var lastData = null;
    var iconsThought = '<svg class="thought-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>';
    var iconsTool = '<svg class="step-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>';
    var iconsCheck = '<svg class="step-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>';
    var iconsError = '<svg class="step-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6"/><path d="M9 9l6 6"/></svg>';
    function renderThoughtSteps(steps) {
      if (!steps || steps.length === 0) return '';
      var html = '<details class="thought-panel" open><summary><span class="thought-icon">' + iconsThought + '</span>Tool calls (' + steps.length + ' step' + (steps.length !== 1 ? 's' : '') + ')</summary><div class="thought-steps">';
      for (var i = 0; i < steps.length; i++) {
        var s = steps[i];
        if (s.type === 'tool_start') {
          html += '<div class="thought-step"><span class="step-icon">' + iconsTool + '</span><div class="step-body"><span class="step-name">' + escapeHtml(s.name) + '</span>' + (s.input ? '<div class="step-in">' + escapeHtml(s.input) + '</div>' : '') + '</div></div>';
        } else if (s.type === 'tool_end') {
          html += '<div class="thought-step tool-end"><span class="step-icon">' + iconsCheck + '</span><div class="step-body"><span class="step-name">' + escapeHtml(s.name) + ' →</span><div class="step-out">' + escapeHtml(s.output) + '</div></div></div>';
        } else if (s.type === 'tool_error') {
          html += '<div class="thought-step tool-error"><span class="step-icon">' + iconsError + '</span><div class="step-body"><span class="step-name">' + escapeHtml(s.name) + '</span><div class="step-out">' + escapeHtml(s.error || '') + '</div></div></div>';
        }
      }
      html += '</div></details>';
      return html;
    }
    function render() {
      fetch('/last').then(r => r.json()).then(data => {
        var stepsStr = (data.steps && data.steps.length) ? JSON.stringify(data.steps) : '';
        var same = lastData && lastData.task === data.task && String(lastData.result) === String(data.result) && (lastData.latency_ms || 0) === (data.latency_ms || 0) && (lastData.steps ? JSON.stringify(lastData.steps) : '') === stepsStr;
        if (same) return;
        lastData = data;
        const el = document.getElementById('chat');
        var wasTaskOpen = el.querySelector('#details-task') && el.querySelector('#details-task').open;
        var wasResponseOpen = el.querySelector('#details-response') && el.querySelector('#details-response').open;
        if (!data.task && !data.result) { el.innerHTML = '<p class="empty">Waiting for tasks from orchestrator…</p>'; return; }
        let html = '';
        if (data.task) {
          var taskOpen = wasTaskOpen ? ' open' : '';
          html += '<div class="msg-card task"><div class="msg-label"><span class="avatar o" title="Orchestrator">O</span>Orchestrator · Task</div><details id="details-task"' + taskOpen + '><summary>Show in chat</summary><div class="msg-content">' + sanitizeHtml(data.task) + '</div></details></div>';
        }
        if (data.result != null) {
          var responseOpen = wasResponseOpen ? ' open' : '';
          var resultContent = sanitizeHtml(data.result) + (data.latency_ms ? '<div class="meta">' + data.latency_ms + ' ms</div>' : '');
          var thoughtHtml = (data.steps && data.steps.length) ? renderThoughtSteps(data.steps) : '';
          html += '<div class="msg-card"><div class="msg-label"><span class="avatar ' + agentCls + '" title="' + agentLabel + '">' + agentLetter + '</span>' + agentLabel + ' · Response</div><details id="details-response"' + responseOpen + '><summary>Show in chat</summary><div class="msg-content">' + resultContent + thoughtHtml + '</div></details></div>';
        }
        el.innerHTML = html || '<p class="empty">Waiting for tasks…</p>';
      }).catch(() => { document.getElementById('chat').innerHTML = '<p class="empty">Could not load last task.</p>'; });
    }
    render();
    setInterval(render, 2500);
  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def agent_ui():
    """Simple chat view for this agent (for orchestrator UI iframe)."""
    return HTMLResponse(_agent_ui_html())


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
