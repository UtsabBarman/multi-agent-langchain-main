#!/usr/bin/env python3
"""Generate a detailed architecture/message-flow PNG in the style of archs.png."""
from __future__ import annotations

import math
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "system-detailed-architecture.png"

WIDTH = 2200
HEIGHT = 1450
BG = "#ECECEC"
BLACK = "#1A1A1A"
GREY = "#BDBDBD"
ORCH = "#CFE2F3"
AGENT = "#D9EAD3"
DATA = "#F8EDC9"
OPS = "#EAD1DC"
WHITE = "#FAFAFA"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend(
            [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Helvetica.ttc",
            ]
        )
    else:
        candidates.extend(
            [
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Supplemental/Helvetica.ttc",
            ]
        )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


TITLE = load_font(34, bold=True)
H1 = load_font(23, bold=True)
H2 = load_font(18, bold=True)
TXT = load_font(15)
SMALL = load_font(13)


def rbox(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, radius: int = 18, width: int = 3) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=BLACK, width=width)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, anchor: str = "la") -> None:
    draw.text(xy, text, fill=BLACK, font=font, anchor=anchor)


def wrapped_block(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    lines: list[str],
    fill: str,
    centered: bool = False,
) -> None:
    x1, y1, x2, y2 = box
    rbox(draw, box, fill)
    if centered:
        label(draw, ((x1 + x2) // 2, y1 + 24), title, H1, anchor="ma")
    else:
        label(draw, ((x1 + x2) // 2, y1 + 24), title, H2, anchor="ma")
    y = y1 + 58
    width_chars = max(20, int((x2 - x1 - 28) / 8.8))
    for item in lines:
        wrapped = textwrap.wrap(item, width=width_chars)
        for part in wrapped:
            label(draw, ((x1 + x2) // 2, y), part, TXT, anchor="ma")
            y += 20
        y += 3
        if y > y2 - 12:
            break


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], width: int = 5) -> None:
    draw.line([start, end], fill=BLACK, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 15
    p1 = (end[0] - size * math.cos(angle - math.pi / 6), end[1] - size * math.sin(angle - math.pi / 6))
    p2 = (end[0] - size * math.cos(angle + math.pi / 6), end[1] - size * math.sin(angle + math.pi / 6))
    draw.polygon([end, p1, p2], fill=BLACK)


def arrow_with_text(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    text: str,
    text_xy: tuple[int, int],
    align: str = "ma",
) -> None:
    arrow(draw, start, end)
    label(draw, text_xy, text, H2, anchor=align)


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    label(draw, (WIDTH // 2, 36), "Multi-Agent System — Detailed Runtime Architecture", TITLE, anchor="ma")

    # Top user bar
    top_user = (300, 85, 1900, 145)
    rbox(draw, top_user, GREY)
    label(draw, ((top_user[0] + top_user[2]) // 2, 114), "User / Browser UI / query_cli / library caller", H2, anchor="ma")

    # Core orchestrator
    orch_box = (300, 235, 1900, 505)
    orch_lines = [
        "• Load domain config + env; optional API key guard",
        "• Persist request, build plan, validate dependencies / detect cycles",
        "• Endpoints: /query, /query/plan, /query/execute, /request/{id}, /respond, /history, /runs/{run_id}/events",
        "• Execute steps in DAG order; call agents over HTTP with run_id + step_id + context",
        "• Retry/backoff, timeout, per-agent circuit breaker, response schema validation",
        "• Persist plan, step_results, run_events; synthesize final HTML answer",
        "• Pause on request_user_validation and resume on user response",
    ]
    wrapped_block(draw, orch_box, "CORE: ORCHESTRATOR (FastAPI, port 8000)", orch_lines, ORCH, centered=True)

    # Agents
    agent1 = (80, 620, 680, 860)
    agent2 = (800, 620, 1400, 860)
    agent3 = (1520, 620, 2120, 860)

    wrapped_block(
        draw,
        agent1,
        "AGENT 1 — RESEARCHER (port 8001)",
        [
            "Tools: search_docs, query_facts, index_doc, request_user_validation",
            "Loads role prompt, guardrails, and clients at startup",
            "Returns result, latency_ms, tool traces, artifacts, validation payload",
        ],
        AGENT,
        centered=True,
    )
    wrapped_block(
        draw,
        agent2,
        "AGENT 2 — ANALYST (port 8002)",
        [
            "Tools: query_facts",
            "Consumes context from prior steps and summarizes / compares facts",
            "Returns structured response to orchestrator",
        ],
        AGENT,
        centered=True,
    )
    wrapped_block(
        draw,
        agent3,
        "AGENT 3 — WRITER (port 8003)",
        [
            "Tools: none",
            "Uses provided context to write final report-style content",
            "Returns HTML-oriented answer fragments and artifacts",
        ],
        AGENT,
        centered=True,
    )

    # Data layer
    data_layer = (80, 980, 2120, 1320)
    rbox(draw, data_layer, DATA)
    label(draw, ((data_layer[0] + data_layer[2]) // 2, 1010), "DATA / TOOLING / PERSISTENCE LAYER", H1, anchor="ma")

    inner1 = (180, 1075, 720, 1185)
    inner2 = (840, 1075, 1360, 1185)
    inner3 = (1480, 1075, 2020, 1185)
    inner4 = (380, 1200, 900, 1290)
    inner5 = (1280, 1200, 1800, 1290)

    wrapped_block(draw, inner1, "SQLite App DB", ["requests", "plans", "step_results", "run_events", "schema_migrations"], WHITE, centered=True)
    wrapped_block(draw, inner2, "Manufacturing SQLite DB", ["read-only facts for query_facts", "opened as SQLite source"], WHITE, centered=True)
    wrapped_block(draw, inner3, "Chroma Vector DB", ["retrieval via search_docs", "indexing via index_doc"], WHITE, centered=True)
    wrapped_block(draw, inner4, "Tool Registry + build_clients()", ["map config tool_names -> tools", "inject SQLite paths / Chroma retriever"], WHITE, centered=True)
    wrapped_block(draw, inner5, "Config + Infra", ["domain JSON, .env, startup.py, migrate.py, Dockerfile, docker-compose"], WHITE, centered=True)

    # Main arrows from user to orchestrator and back
    arrow_with_text(
        draw,
        ((top_user[0] + top_user[2]) // 2, top_user[3]),
        ((top_user[0] + top_user[2]) // 2, orch_box[1]),
        "① POST /query or POST /query/plan { query }",
        (630, 190),
        "la",
    )
    arrow_with_text(
        draw,
        ((top_user[0] + top_user[2]) // 2 + 110, orch_box[1]),
        ((top_user[0] + top_user[2]) // 2 + 110, top_user[3]),
        "⑦ Response / polling / UI trace { request_id, status, final_answer }",
        (1190, 190),
        "la",
    )

    # Orchestrator <-> agents
    orch_bottom_y = orch_box[3]
    a1_mid = ((agent1[0] + agent1[2]) // 2, agent1[1])
    a2_mid = ((agent2[0] + agent2[2]) // 2, agent2[1])
    a3_mid = ((agent3[0] + agent3[2]) // 2, agent3[1])

    arrow(draw, (a1_mid[0], orch_bottom_y), a1_mid)
    arrow(draw, (a1_mid[0] + 40, agent1[1]), (a1_mid[0] + 40, orch_bottom_y))
    label(draw, (a1_mid[0] - 180, 560), "② POST /invoke\n{ task, context,\nrun_id, step_id }", H2, anchor="ma")
    label(draw, (a1_mid[0] + 165, 560), "③ HTTP 200\n{ result, status,\nlatency_ms, artifacts,\nrequires_validation? }", H2, anchor="ma")

    arrow(draw, (a2_mid[0], orch_bottom_y), a2_mid)
    arrow(draw, (a2_mid[0] + 40, agent2[1]), (a2_mid[0] + 40, orch_bottom_y))
    label(draw, (a2_mid[0] - 180, 560), "② POST /invoke\nDAG-ordered step", H2, anchor="ma")
    label(draw, (a2_mid[0] + 170, 560), "③ Validated agent response", H2, anchor="ma")

    arrow(draw, (a3_mid[0], orch_bottom_y), a3_mid)
    arrow(draw, (a3_mid[0] + 40, agent3[1]), (a3_mid[0] + 40, orch_bottom_y))
    label(draw, (a3_mid[0] - 165, 560), "② POST /invoke\nwriter/report step", H2, anchor="ma")
    label(draw, (a3_mid[0] + 165, 560), "③ Final agent output", H2, anchor="ma")

    # Agents to data layer
    for box, xshift in ((agent1, -40), (agent2, 0), (agent3, 40)):
        midx = (box[0] + box[2]) // 2 + xshift
        arrow(draw, (midx, box[3]), (midx, data_layer[1]))
        arrow(draw, (midx + 26, data_layer[1]), (midx + 26, box[3]))

    # Detail labels around data access
    label(draw, (270, 900), "④ researcher -> search_docs / query_facts / index_doc", H2, anchor="ma")
    label(draw, (1095, 900), "④ analyst -> query_facts", H2, anchor="ma")
    label(draw, (1810, 900), "④ writer -> no direct tools", H2, anchor="ma")

    # Pause / resume callout
    pause_box = (1820, 360, 2130, 560)
    wrapped_block(
        draw,
        pause_box,
        "Pause / Resume Path",
        [
            "⑤ request_user_validation may pause run",
            "Request stored as awaiting_user_input",
            "POST /request/{id}/respond resumes execution",
        ],
        WHITE,
        centered=True,
    )
    arrow(draw, (1900, 505), (1900, 560))

    # Bottom flow strip like original
    strip = (80, 1350, 2120, 1410)
    rbox(draw, strip, GREY)
    label(
        draw,
        ((strip[0] + strip[2]) // 2, (strip[1] + strip[3]) // 2),
        "Flow: Query -> Plan -> Validate DAG -> Invoke Agents -> Use Tools/Data -> Persist State/Events -> Report Final Answer",
        H2,
        anchor="ma",
    )

    img.save(OUTPUT, "PNG")
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
