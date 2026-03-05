"""Orchestrator FastAPI app: POST /query -> plan, execute, report."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Load .env so SQLITE_APP_PATH etc. are set when orchestrator runs (standalone or via startup.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_PROJECT_ROOT / "config" / "env" / ".env", _PROJECT_ROOT / ".env"):
    if _p.exists():
        load_dotenv(_p, override=False)
        break

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("orchestrator")
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.responses import JSONResponse

from src.core.config.loader import load_domain_config
from src.core.contracts.gateway import QueryRequest, QueryResponse
from src.core.contracts.orchestrator import Plan, StepResult
from src.data_access.app_db import open_app_db_connection
from src.orchestrator.session import (
    create_request,
    update_request_final,
    save_plan,
    save_step_result,
    get_request,
    get_plan,
    get_step_results,
    get_latest_request_id,
)
from src.orchestrator.planner import build_plan
from src.orchestrator.executor import run_plan, run_step
from src.orchestrator.reporter import synthesize_final_answer

app = FastAPI(title="Multi-Agent: Orchestrator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/domains/manufacturing.json")
PROJECT_ROOT = _PROJECT_ROOT
DOMAIN_CONFIG = None


def get_config():
    global DOMAIN_CONFIG
    if DOMAIN_CONFIG is None:
        DOMAIN_CONFIG = load_domain_config(CONFIG_PATH, project_root=PROJECT_ROOT)
    return DOMAIN_CONFIG


@app.on_event("startup")
def startup():
    get_config()


@app.get("/health")
def health():
    return {"status": "ok"}


def _orchestrator_ui_html() -> str:
    """Orchestrator chat UI with agent iframes; labels and icons from domain config."""
    config = get_config()
    agents = config.agents
    # CSS class for avatar color: use name for known agents, else "unknown"
    def _avatar_cls(a) -> str:
        return a.name if a.name in ("researcher", "analyst", "writer") else "unknown"
    iframe_parts = []
    for i, a in enumerate(agents):
        n = i + 1
        label = a.get_display_label()
        letter = a.get_icon_letter()
        cls = _avatar_cls(a)
        iframe_parts.append(
            f'<div class="iframe-wrap" id="agent{n}-wrap">'
            f'<div class="iframe-head"><span class="plan-avatar {html.escape(cls)}" title="{html.escape(label)}">{html.escape(letter)}</span>'
            f'<span>{html.escape(label)}</span></div>'
            f'<iframe id="agent{n}" title="{html.escape(label)}"></iframe></div>'
        )
    iframes_html = "\n      ".join(iframe_parts)
    iframe_src_lines = "\n    ".join(
        f"document.getElementById('agent{i+1}').src = base + ':{a.port}/';"
        for i, a in enumerate(agents)
    )
    agent_meta = {
        a.name.lower(): {
            "label": a.get_display_label(),
            "letter": a.get_icon_letter(),
            "cls": _avatar_cls(a),
            "iframeNum": i + 1,
        }
        for i, a in enumerate(agents)
    }
    agent_meta_js = json.dumps(agent_meta)
    return (
        r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Orchestrator</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, sans-serif; background: #343541; color: #ececec; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
    .header { padding: 0.75rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.95rem; font-weight: 600; flex-shrink: 0; }
    .main { display: flex; flex: 1; min-height: 0; overflow: hidden; }
    .chat-col { flex: 1; display: flex; flex-direction: column; min-width: 0; border-right: 1px solid rgba(255,255,255,0.08); overflow: hidden; }
    .chat { flex: 1; overflow-y: auto; padding: 1rem; max-width: 42rem; margin: 0 auto; width: 100%; min-height: 0; }
    .iframes { width: 420px; display: flex; flex-direction: column; background: #2d2d30; flex-shrink: 0; min-height: 0; overflow-y: auto; }
    .iframes h2 { font-size: 0.8rem; margin: 0; padding: 0.5rem 0.75rem; color: #8e8ea0; font-weight: 600; border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0; }
    .iframe-wrap { flex: 0 0 auto; min-height: 140px; height: 220px; display: flex; flex-direction: column; border-bottom: 1px solid rgba(255,255,255,0.06); transition: box-shadow 0.25s ease; }
    .iframe-wrap:last-child { border-bottom: none; }
    .iframe-wrap.highlight { box-shadow: inset 0 0 0 2px #19c37d; }
    .iframe-wrap iframe { flex: 1; width: 100%; min-height: 0; border: none; background: #2d2d30; }
    .iframe-head { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.75rem; font-size: 0.75rem; font-weight: 600; color: #e4e4e7; background: rgba(0,0,0,0.2); border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0; }
    .iframe-head .plan-avatar { width: 20px; height: 20px; font-size: 0.65rem; }
    .message { display: flex; gap: 0.75rem; margin-bottom: 1rem; align-items: flex-start; }
    .message .content { flex: 1; min-width: 0; }
    .message .avatar { width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600; }
    .message.user .avatar { background: #19c37d; }
    .message.assistant .avatar { background: #8e8ea0; }
    .message .bubble { max-width: 85%; padding: 0.75rem 1rem; border-radius: 12px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: break-word; word-break: normal; }
    .message.user .bubble { background: #2f2f3a; border: 1px solid rgba(255,255,255,0.08); }
    .message.assistant .bubble { background: #40414f; border: 1px solid rgba(255,255,255,0.08); }
    .message.assistant.error .bubble { color: #f87171; }
    .message .meta { font-size: 0.7rem; color: #8e8ea0; margin-top: 0.35rem; }
    .section-card { margin-top: 0.75rem; max-width: 85%; border-radius: 12px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); }
    .section-card summary { cursor: pointer; list-style: none; user-select: none; }
    .section-card summary::-webkit-details-marker { display: none; }
    .section-header { padding: 0.6rem 0.85rem; font-size: 0.8rem; font-weight: 600; color: #a0a0b0; display: flex; align-items: center; gap: 0.5rem; background: rgba(0,0,0,0.2); }
    .section-header .icon { opacity: 0.9; }
    .plan-steps { padding: 0.5rem 0.85rem 0.75rem; background: rgba(0,0,0,0.15); }
    .plan-step { display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.4rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.8rem; }
    .plan-step:last-child { border-bottom: none; }
    .plan-avatar { width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 600; }
    .plan-avatar.researcher { background: #0d9488; color: #fff; }
    .plan-avatar.analyst { background: #6366f1; color: #fff; }
    .plan-avatar.writer { background: #d97706; color: #fff; }
    .plan-avatar.unknown { background: #52525b; color: #fff; }
    .plan-step-title { flex: 1; min-width: 0; color: #e4e4e7; }
    .plan-step-num { color: #71717a; margin-right: 0.25rem; }
    .live-progress { margin-top: 0.6rem; max-width: 85%; padding: 0.5rem 0.75rem; background: rgba(0,0,0,0.2); border-radius: 10px; border: 1px solid rgba(255,255,255,0.08); font-size: 0.8rem; }
    .live-progress .step-live { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0; }
    .live-progress .step-live .step-dot { width: 18px; height: 18px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 0.65rem; }
    .live-progress .step-live.running .step-dot { background: rgba(25,195,125,0.3); animation: pulse 1s ease-in-out infinite; }
    .live-progress .step-live.done .step-dot { background: #19c37d; color: #fff; }
    .live-progress .step-live.pending .step-dot { background: #3f3f46; color: #71717a; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
    .reporter-card { margin-top: 0.75rem; max-width: 85%; border-radius: 12px; padding: 0.85rem 1rem; background: rgba(25,195,125,0.08); border: 1px solid rgba(25,195,125,0.25); border-left: 4px solid #19c37d; }
    .reporter-card.error { background: rgba(248,113,113,0.08); border-color: rgba(248,113,113,0.3); border-left-color: #f87171; }
    .reporter-card .reporter-label { font-size: 0.7rem; font-weight: 600; color: #19c37d; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.4rem; }
    .reporter-card.error .reporter-label { color: #f87171; }
    .reporter-card .reporter-content { font-size: 0.9rem; line-height: 1.5; color: #e4e4e7; word-break: break-word; }
    .reporter-card .reporter-content p { margin: 0 0 0.6rem; }
    .reporter-card .reporter-content p:last-child { margin-bottom: 0; }
    .reporter-card .reporter-content h2 { font-size: 1rem; margin: 1rem 0 0.5rem; font-weight: 600; }
    .reporter-card .reporter-content h3 { font-size: 0.95rem; margin: 0.75rem 0 0.4rem; font-weight: 600; }
    .reporter-card .reporter-content ul, .reporter-card .reporter-content ol { margin: 0.4rem 0; padding-left: 1.25rem; }
    .reporter-card .reporter-content li { margin-bottom: 0.25rem; }
    .reporter-card .reporter-content a { color: #19c37d; text-decoration: none; }
    .reporter-card .reporter-content a:hover { text-decoration: underline; }
    .reporter-card .reporter-content blockquote { margin: 0.5rem 0; padding-left: 1rem; border-left: 3px solid rgba(255,255,255,0.2); color: #a1a1aa; }
    .reporter-card details { margin-top: 0.25rem; }
    .reporter-card details summary { cursor: pointer; font-size: 0.8rem; color: #19c37d; list-style: none; display: flex; align-items: center; gap: 0.35rem; }
    .reporter-card details summary::-webkit-details-marker { display: none; }
    .reporter-card details summary::before { content: "▶"; font-size: 0.6rem; transition: transform 0.15s; }
    .reporter-card details[open] summary::before { transform: rotate(90deg); }
    .empty-state { text-align: center; color: #8e8ea0; padding: 2rem 1rem; font-size: 0.95rem; }
    .input-wrap { padding: 1rem; background: #343541; border-top: 1px solid rgba(255,255,255,0.08); }
    .input-inner { max-width: 42rem; margin: 0 auto; display: flex; gap: 0.5rem; align-items: center; background: #40414f; border: 1px solid rgba(255,255,255,0.15); border-radius: 24px; padding: 0.6rem 1rem; }
    .input-inner:focus-within { border-color: #19c37d; box-shadow: 0 0 0 1px #19c37d; }
    #query { flex: 1; min-width: 0; background: none; border: none; color: #ececec; font-size: 1rem; padding: 0.4rem 0; outline: none; }
    #query::placeholder { color: #8e8ea0; }
    #send { background: #19c37d; color: #fff; border: none; width: 36px; height: 36px; border-radius: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    #send:hover { background: #1a7f4b; }
    #send:disabled { opacity: 0.5; cursor: not-allowed; }
    .typing { display: flex; gap: 4px; padding: 0.5rem 0; }
    .typing span { width: 6px; height: 6px; background: #8e8ea0; border-radius: 50%; animation: dot 1.4s ease-in-out infinite both; }
    .typing span:nth-child(2) { animation-delay: 0.2s; }
    .typing span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes dot { 0%,80%,100% { transform: scale(0.6); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }
  </style>
</head>
<body>
  <header class="header">Orchestrator</header>
  <div class="main">
    <div class="chat-col">
      <div class="chat" id="chat">
        <div class="empty-state" id="empty">Ask anything. The orchestrator will plan steps and delegate to the agents on the right.</div>
        <div id="messages"></div>
      </div>
      <div class="input-wrap">
        <div class="input-inner">
          <input type="text" id="query" placeholder="Message…" autocomplete="off">
          <button type="button" id="send" aria-label="Send"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg></button>
        </div>
      </div>
    </div>
    <div class="iframes">
      <h2>Agents</h2>
      __IFRAMES_HTML__
    </div>
  </div>
  <script>
    var host = window.location.hostname;
    if (host === '0.0.0.0' || host === '' || host === 'localhost') host = '127.0.0.1';
    var base = window.location.protocol + '//' + host;
    __IFRAME_SRC_SCRIPT__
    var chatEl = document.getElementById('chat');
    var emptyEl = document.getElementById('empty');
    var messagesEl = document.getElementById('messages');
    var queryEl = document.getElementById('query');
    var sendBtn = document.getElementById('send');
    function escapeHtml(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
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
    var agentMeta = __AGENT_META_JS__;
    function getAgentMeta(name) {
      var key = (name || '').toLowerCase();
      return agentMeta[key] || { label: (name || 'Agent').replace(/^./, function(c) { return c.toUpperCase(); }), letter: (name || '?').charAt(0).toUpperCase(), cls: 'unknown', iframeNum: 1 };
    }
    function addUserMessage(q) {
      emptyEl.style.display = 'none';
      var div = document.createElement('div');
      div.className = 'message user';
      div.innerHTML = '<span class="avatar">U</span><div class="content"><div class="bubble">' + escapeHtml(q) + '</div></div>';
      messagesEl.appendChild(div);
      chatEl.scrollTop = chatEl.scrollHeight;
    }
    function addLiveReplyContainer() {
      var contentDiv = document.createElement('div');
      contentDiv.className = 'content';
      contentDiv.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
      var msgDiv = document.createElement('div');
      msgDiv.className = 'message assistant';
      msgDiv.id = 'live-reply';
      msgDiv.innerHTML = '<span class="avatar">O</span>';
      msgDiv.appendChild(contentDiv);
      messagesEl.appendChild(msgDiv);
      chatEl.scrollTop = chatEl.scrollHeight;
      return contentDiv;
    }
    function renderLiveReply(trace, liveEl) {
      var planSteps = (trace.plan && trace.plan.steps) ? trace.plan.steps : [];
      var stepResults = trace.step_results || [];
      var status = trace.status || 'running';
      var finalAnswer = trace.final_answer != null ? trace.final_answer : (trace.error_message || '');
      var isDone = status === 'completed' || status === 'failed' || status === 'partial';
      var resultByIdx = {};
      for (var ri = 0; ri < stepResults.length; ri++) resultByIdx[stepResults[ri].step_index] = stepResults[ri];
      var blocks = '';
      if (planSteps.length) {
        var planIcon = '<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>';
        blocks += '<details class="section-card" open><summary><span class="section-header">' + planIcon + ' Plan (' + planSteps.length + ' steps)</span></summary><div class="plan-steps">';
        for (var i = 0; i < planSteps.length; i++) {
          var s = planSteps[i];
          var am = getAgentMeta(s.agent_name);
          var taskTitle = (s.task_description || '').slice(0, 80);
          if ((s.task_description || '').length > 80) taskTitle += '…';
          blocks += '<div class="plan-step"><span class="plan-avatar ' + am.cls + '" title="' + escapeHtml(am.label) + '">' + am.letter + '</span><span class="plan-step-title"><span class="plan-step-num">Step ' + (s.step_index || (i + 1)) + '</span>' + escapeHtml(am.label) + ' — ' + escapeHtml(taskTitle) + '</span></div>';
        }
        blocks += '</div></details>';
        blocks += '<div class="live-progress">';
        for (var j = 0; j < planSteps.length; j++) {
          var s2 = planSteps[j];
          var am2 = getAgentMeta(s2.agent_name);
          var done = resultByIdx[s2.step_index];
          var running = !isDone && stepResults.length === j;
          var cls = done ? 'done' : (running ? 'running' : 'pending');
          var label = done ? am2.label + ' ✓' : (running ? 'Sending to ' + am2.label + '…' : am2.label);
          blocks += '<div class="step-live ' + cls + '"><span class="step-dot">' + (done ? '✓' : (running ? '…' : '·')) + '</span><span>' + escapeHtml(label) + '</span></div>';
        }
        blocks += '</div>';
      } else {
        blocks += '<div class="typing"><span></span><span></span><span></span></div>';
      }
      if (isDone) {
        var previewLen = 180;
        var full = finalAnswer || '';
        var isShort = full.length <= previewLen;
        if (isShort) {
          blocks += '<div class="reporter-card' + (status !== 'completed' ? ' error' : '') + '"><div class="reporter-label">Reporter · Final answer</div><div class="reporter-content">' + sanitizeHtml(full) + '</div></div>';
        } else {
          blocks += '<div class="reporter-card' + (status !== 'completed' ? ' error' : '') + '"><div class="reporter-label">Reporter · Final answer</div><details><summary>Show in chat</summary><div class="reporter-content">' + sanitizeHtml(full) + '</div></details></div>';
        }
      }
      liveEl.innerHTML = blocks;
      chatEl.scrollTop = chatEl.scrollHeight;
    }
    function reloadAgentIframe(num) {
      var iframe = document.getElementById('agent' + num);
      if (iframe && iframe.src) iframe.src = iframe.src;
    }
    var pollIntervalMs = 700;
    var pollTimeoutMs = 120000;
    async function submit() {
      var q = queryEl.value.trim();
      if (!q) return;
      queryEl.value = '';
      addUserMessage(q);
      var prevLive = document.getElementById('live-reply');
      if (prevLive) {
        prevLive.id = '';
        var prevContent = prevLive.querySelector('.content');
        if (prevContent) prevContent.innerHTML = '<div class="bubble" style="color:#8e8ea0;">—</div>';
      }
      sendBtn.disabled = true;
      var liveEl = addLiveReplyContainer();
      try {
        var r = await fetch('/query/async', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: q }) });
        if (r.status !== 202) {
          var err = await r.json().catch(function() { return {}; });
          liveEl.innerHTML = '<div class="reporter-card error"><div class="reporter-label">Error</div><div class="reporter-content">' + escapeHtml(err.detail || 'Request failed') + '</div></div>';
          sendBtn.disabled = false;
          return;
        }
        var data = await r.json();
        var requestId = data.request_id;
        var lastStepCount = 0;
        var start = Date.now();
        function poll() {
          if (Date.now() - start > pollTimeoutMs) {
            liveEl.innerHTML = '<div class="reporter-card error"><div class="reporter-label">Timeout</div><div class="reporter-content">Request took too long.</div></div>';
            sendBtn.disabled = false;
            return;
          }
          fetch('/request/' + requestId).then(function(tr) { return tr.json(); }).then(function(trace) {
            renderLiveReply(trace, liveEl);
            var stepResults = trace.step_results || [];
            if (stepResults.length > lastStepCount) {
              for (var i = lastStepCount; i < stepResults.length; i++) {
                var an = (stepResults[i].agent_name || '').toLowerCase();
                var num = (agentMeta[an] && agentMeta[an].iframeNum) ? agentMeta[an].iframeNum : (i + 1);
                reloadAgentIframe(num);
              }
              lastStepCount = stepResults.length;
            }
            var status = trace.status || 'running';
            if (status !== 'running' && status !== 'pending') {
              sendBtn.disabled = false;
              var msgDiv = liveEl.closest('.message');
              if (msgDiv && msgDiv.id === 'live-reply') msgDiv.id = '';
              return;
            }
            setTimeout(poll, pollIntervalMs);
          }).catch(function(e) {
            liveEl.innerHTML = '<div class="reporter-card error"><div class="reporter-label">Error</div><div class="reporter-content">' + escapeHtml(e.message || 'Poll failed') + '</div></div>';
            sendBtn.disabled = false;
          });
        }
        setTimeout(poll, pollIntervalMs);
      } catch (e) {
        liveEl.innerHTML = '<div class="reporter-card error"><div class="reporter-label">Error</div><div class="reporter-content">' + escapeHtml(e.message || 'Request failed') + '</div></div>';
        sendBtn.disabled = false;
      }
    }
    sendBtn.addEventListener('click', submit);
    queryEl.addEventListener('keydown', function(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
  </script>
</body>
</html>"""
        .replace("__IFRAMES_HTML__", iframes_html)
        .replace("__IFRAME_SRC_SCRIPT__", iframe_src_lines)
        .replace("__AGENT_META_JS__", agent_meta_js)
    )


@app.get("/", response_class=HTMLResponse)
def orchestrator_ui():
    """Orchestrator chat UI with 3 agent iframes (Option B)."""
    return HTMLResponse(_orchestrator_ui_html())


@app.get("/request/{request_id}")
async def get_request_trace(request_id: str):
    """Return full trace for a request: request, plan, step_results. For Chat UI flow and internal chat."""
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")
    env = dict(os.environ)
    try:
        conn = await open_app_db_connection(env)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        req = await get_request(conn, rid)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        plan = await get_plan(conn, rid)
        step_results = await get_step_results(conn, rid)
    finally:
        await conn.close()
    steps = [s.model_dump() for s in plan.steps] if plan else []
    return {
        "request_id": req["id"],
        "query": req["query"],
        "status": req["status"],
        "final_answer": req["final_answer"],
        "error_message": req["error_message"],
        "created_at": req["created_at"],
        "plan": {"steps": steps},
        "step_results": step_results,
    }


@app.get("/trace/last")
async def get_trace_last(domain_id: str | None = None):
    """Return full trace for the most recent request (optional domain_id filter). For Chat UI."""
    env = dict(os.environ)
    try:
        conn = await open_app_db_connection(env)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        rid = await get_latest_request_id(conn, domain_id)
        if not rid:
            raise HTTPException(status_code=404, detail="No requests found")
        req = await get_request(conn, rid)
        plan = await get_plan(conn, rid)
        step_results = await get_step_results(conn, rid)
    finally:
        await conn.close()
    steps = [s.model_dump() for s in plan.steps] if plan else []
    return {
        "request_id": req["id"],
        "query": req["query"],
        "status": req["status"],
        "final_answer": req["final_answer"],
        "error_message": req["error_message"],
        "created_at": req["created_at"],
        "plan": {"steps": steps},
        "step_results": step_results,
    }


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    config = get_config()
    domain_id = req.domain_id or config.domain_id
    env = dict(os.environ)

    log.info("QUERY: %s", (req.query[:200] + "…") if len(req.query) > 200 else req.query)

    try:
        conn = await open_app_db_connection(env)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        request_id = await create_request(conn, domain_id, req.query, req.session_id)
    finally:
        await conn.close()

    try:
        plan = build_plan(req.query, config)
    except Exception as e:
        log.exception("Plan failed")
        await _update_status(env, request_id, "failed", error_message=str(e))
        return QueryResponse(request_id=str(request_id), status="failed", error=str(e))

    for i, s in enumerate(plan.steps, 1):
        log.info("PLAN step %s → %s: %s", i, s.agent_name, (s.task_description[:80] + "…") if len(s.task_description) > 80 else s.task_description)

    conn = await open_app_db_connection(env)
    try:
        await save_plan(conn, request_id, plan)
    finally:
        await conn.close()

    step_results = await run_plan(plan, req.query, config)

    conn = await open_app_db_connection(env)
    try:
        step_by_idx = {s.step_index: s for s in plan.steps}
        for sr in step_results:
            step = step_by_idx.get(sr.step_index)
            task_desc = step.task_description if step else ""
            await save_step_result(
                conn,
                request_id,
                sr.step_index,
                sr.agent_name,
                {"task": task_desc},
                sr.output,
                sr.status,
                sr.latency_ms,
            )
    finally:
        await conn.close()

    try:
        final_answer = synthesize_final_answer(req.query, step_results)
    except Exception as e:
        log.exception("Synthesis failed")
        await _update_status(env, request_id, "partial", error_message=str(e))
        return QueryResponse(request_id=str(request_id), status="partial", final_answer=None, error=str(e))

    log.info("FINAL ANSWER: %s", (final_answer[:300] + "…") if final_answer and len(final_answer) > 300 else (final_answer or "(empty)"))
    await _update_status(env, request_id, "completed", final_answer=final_answer)
    return QueryResponse(request_id=str(request_id), status="completed", final_answer=final_answer)


async def _update_status(env: dict, request_id, status: str, final_answer: str | None = None, error_message: str | None = None):
    conn = await open_app_db_connection(env)
    try:
        await update_request_final(conn, request_id, status, final_answer=final_answer, error_message=error_message)
    finally:
        await conn.close()


async def _run_query_background(request_id: uuid.UUID, query: str, config, env: dict):
    """Run plan step-by-step, saving after each step so the UI can poll and show live progress."""
    try:
        plan = build_plan(query, config)
        for i, s in enumerate(plan.steps, 1):
            log.info("PLAN step %s → %s: %s", i, s.agent_name, (s.task_description[:80] + "…") if len(s.task_description) > 80 else s.task_description)
        conn = await open_app_db_connection(env)
        try:
            await save_plan(conn, request_id, plan)
        finally:
            await conn.close()

        context_parts = [f"Original query: {query}"]
        step_results: list[StepResult] = []
        for step in plan.steps:
            context = "\n".join(context_parts)
            sr = await run_step(step, context, config)
            step_results.append(sr)
            conn = await open_app_db_connection(env)
            try:
                await save_step_result(
                    conn,
                    request_id,
                    sr.step_index,
                    sr.agent_name,
                    {"task": step.task_description},
                    sr.output,
                    sr.status,
                    sr.latency_ms,
                )
            finally:
                await conn.close()
            context_parts.append(f"Step {step.step_index} ({step.agent_name}): {sr.output}")

        final_answer = synthesize_final_answer(query, step_results)
        log.info("FINAL ANSWER: %s", (final_answer[:300] + "…") if final_answer and len(final_answer) > 300 else (final_answer or "(empty)"))
        await _update_status(env, request_id, "completed", final_answer=final_answer)
    except Exception as e:
        log.exception("Background query failed")
        await _update_status(env, request_id, "failed", error_message=str(e))


@app.post("/query/async")
async def query_async(req: QueryRequest):
    """Start query in background; returns request_id immediately. Poll GET /request/{request_id} for live progress."""
    config = get_config()
    domain_id = req.domain_id or config.domain_id
    env = dict(os.environ)
    try:
        conn = await open_app_db_connection(env)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        request_id = await create_request(conn, domain_id, req.query, req.session_id)
    finally:
        await conn.close()

    log.info("QUERY (async): %s", (req.query[:200] + "…") if len(req.query) > 200 else req.query)
    asyncio.create_task(_run_query_background(request_id, req.query, config, env))
    return JSONResponse(status_code=202, content={"request_id": str(request_id)})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
