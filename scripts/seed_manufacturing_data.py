#!/usr/bin/env python3
"""Seed manufacturing SQLite DB and Chroma with sample data. Run after migrate.py.
   Requires: SQLITE_MANUFACTURING_PATH, CHROMA_PATH, OPENAI_API_KEY in .env
   Usage: PYTHONPATH=. python scripts/seed_manufacturing_data.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config.env import ensure_project_env

ensure_project_env(ROOT)
env = dict(os.environ)


MANUFACTURING_SQL = """
-- Windmill Manufacturing sample schema and data
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS safety_guidelines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    topic TEXT NOT NULL,
    guideline_text TEXT NOT NULL,
    category TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS procedures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    department TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quality_standards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    level TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO products (id, name, category, description) VALUES
(1, 'Product X', 'Assembly', 'Main assembly line product X with standard safety requirements'),
(2, 'Product Y', 'Electronics', 'Electronic component product Y'),
(3, 'Product Z', 'Packaging', 'Packaging line product Z');

INSERT OR IGNORE INTO safety_guidelines (id, product_id, topic, guideline_text, category) VALUES
(1, 1, 'Personal protective equipment', 'All personnel must wear PPE (helmet, safety glasses, gloves) when on the assembly floor for Product X.', 'PPE'),
(2, 1, 'Machine guarding', 'Guards must be in place before operating any machine on the Product X line. Never bypass guards.', 'Machinery'),
(3, 1, 'Emergency stops', 'Know the location of emergency stop buttons. Use them only in case of immediate danger.', 'Emergency'),
(4, 2, 'ESD protection', 'Use ESD wrist straps and mats when handling Product Y components. Ground yourself before touching boards.', 'Electrostatic'),
(5, 2, 'Ventilation', 'Soldering and chemical work for Product Y must be done in well-ventilated areas.', 'Ventilation'),
(6, NULL, 'General housekeeping', 'Keep walkways clear. Report spills and obstructions immediately.', 'General'),
(7, 3, 'Lifting', 'Use proper lifting technique for Product Z packaging. Do not lift over 25 kg alone.', 'Ergonomics');

INSERT OR IGNORE INTO procedures (id, name, description, department) VALUES
(1, 'Start-of-shift checklist', 'Complete the start-of-shift safety and equipment checklist before beginning work.', 'Operations'),
(2, 'Quality inspection', 'Inspect first article and every 10th unit per quality inspection procedure QI-101.', 'Quality'),
(3, 'Maintenance lockout', 'Follow lockout/tagout procedure LOTO-01 before any maintenance on powered equipment.', 'Maintenance'),
(4, 'Incident reporting', 'Report any incident or near-miss within 24 hours using form IR-01.', 'Safety'),
(5, 'Document control', 'Use only approved, current versions of work instructions from the document control system.', 'Quality');

INSERT OR IGNORE INTO quality_standards (id, name, description, level) VALUES
(1, 'Dimensional tolerance', 'Parts must be within ±0.1 mm of nominal unless otherwise specified on the drawing.', 'Standard'),
(2, 'Surface finish', 'Surface finish Ra ≤ 1.6 µm for mating surfaces per ISO 1302.', 'Standard'),
(3, 'Traceability', 'Batch and serial traceability required for Product X and Product Y per customer requirements.', 'Required'),
(4, 'First article inspection', 'First article inspection required for all new or changed product introductions.', 'Required');
"""

CHROMA_DOCS = [
    (
        "safety_overview",
        """# Windmill Manufacturing – Safety Overview

## Core safety guidelines

All employees must follow these guidelines on the manufacturing floor.

**Personal protective equipment (PPE)**  
Wear the PPE specified for your area: safety glasses, hearing protection where posted, gloves when handling sharp or hot items, and safety shoes in production areas. For Product X assembly, helmet and gloves are mandatory.

**Machine safety**  
Do not operate machinery without training and authorization. Guards must be in place. Never reach into moving equipment. Use lockout/tagout (LOTO) before any maintenance or clearing of jams.

**Emergency response**  
Know the location of emergency exits, first-aid kits, and emergency stop buttons. In case of fire, use the nearest pull station and evacuate via the marked route. Report all incidents to your supervisor and via the incident reporting system.

**Housekeeping**  
Keep walkways and work areas clear. Report spills, damaged equipment, or hazards immediately. Good housekeeping reduces slips, trips, and fires."""
    ),
    (
        "product_x_quality",
        """# Product X – Quality and Inspection

Product X is our main assembly-line product. Quality requirements are as follows.

**Inspection frequency**  
First article inspection is required at job start and after any change (tool, material, or operator). In-process inspection: every 10th unit. Full dimensional and visual check per work instruction WI-X-02.

**Key dimensions**  
Critical dimensions are marked on the drawing. Tolerance is ±0.1 mm unless otherwise specified. Use calibrated gauges and document results on the inspection sheet.

**Defect handling**  
If a defect is found, stop the line if required by the control plan. Segregate suspect parts. Notify quality and production. Do not ship non-conforming product. Rework or scrap per disposition from quality."""
    ),
    (
        "maintenance_procedures",
        """# Maintenance Procedures – Manufacturing

**Preventive maintenance**  
Follow the preventive maintenance schedule in the CMMS. Complete PM checklists and log labor and parts. Defer only with approval from maintenance and production.

**Lockout/tagout (LOTO)**  
Before any work on powered equipment (electrical, pneumatic, hydraulic), the authorized person must: isolate energy sources, apply locks and tags, verify zero energy, then perform the work. Remove locks only after the same person has verified the area is clear. Procedure LOTO-01 must be followed every time.

**Spare parts**  
Critical spare parts are listed in the maintenance store. Reorder when minimum stock is reached. Use the correct part number; do not substitute without engineering approval."""
    ),
    (
        "environmental_and_waste",
        """# Environmental and Waste – Manufacturing

**Waste segregation**  
Separate recyclables (cardboard, metal, plastic per local rules), hazardous waste (oils, chemicals, batteries), and general waste. Use the correct bins and labels. Do not mix streams.

**Chemical handling**  
Use only approved chemicals. Read the SDS before use. Wear the PPE indicated on the SDS and the area poster. Store chemicals in designated areas and keep containers closed. Report leaks or spills to the environmental coordinator.

**Energy**  
Turn off equipment and lights when not in use. Report compressed air leaks. These measures support our environmental objectives and reduce cost."""
    ),
]


async def seed_sqlite(db_path: str) -> None:
    path = Path(db_path)
    if not path.is_absolute():
        path = (ROOT / db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    import aiosqlite
    conn = await aiosqlite.connect(str(path))
    try:
        for stmt in MANUFACTURING_SQL.split(";"):
            stmt = stmt.strip()
            # Strip leading comment lines so "-- ...\nCREATE TABLE" is executed
            lines = stmt.split("\n")
            while lines and lines[0].strip().startswith("--"):
                lines.pop(0)
            stmt = "\n".join(lines).strip()
            if stmt:
                await conn.execute(stmt + ";")
        await conn.commit()
        print(f"  SQLite: {path} seeded (products, safety_guidelines, procedures, quality_standards).")
    finally:
        await conn.close()


def seed_chroma(chroma_path: str, collection_name: str = "manufacturing_docs") -> None:
    from src.data_access.vector.indexing import index_text_to_chroma
    path = Path(chroma_path)
    if not path.is_absolute():
        path = (ROOT / chroma_path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    total = 0
    for source, text in CHROMA_DOCS:
        n = index_text_to_chroma(str(path), collection_name, text, source=source)
        total += n
        print(f"  Chroma: indexed {n} chunks from '{source}'.")
    print(f"  Chroma: {path} collection '{collection_name}' total {total} chunks.")


async def main() -> None:
    db_path = env.get("SQLITE_MANUFACTURING_PATH", "").strip() or "./data/manufacturing.sqlite"
    chroma_path = env.get("CHROMA_PATH", "").strip() or "./data/chroma"
    if not db_path:
        print("SQLITE_MANUFACTURING_PATH not set. Set it in config/env/.env or .env")
        sys.exit(1)
    print("Seeding manufacturing data...")
    await seed_sqlite(db_path)
    if chroma_path and env.get("OPENAI_API_KEY"):
        try:
            seed_chroma(chroma_path)
        except Exception as e:
            print(f"  Chroma seed failed (need OPENAI_API_KEY and network): {e}")
            print("  You can later upload .txt/.md files via the Orchestrator UI Doc Store.")
    else:
        print("  Chroma: skipped (set CHROMA_PATH and OPENAI_API_KEY to seed documents).")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
