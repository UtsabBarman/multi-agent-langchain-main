"""Doc Store (Chroma) and DB Store (SQLite) API for the orchestrator UI."""
from __future__ import annotations

import logging
import os

import chromadb
from fastapi import APIRouter, File, HTTPException, UploadFile

from src.data_access.vector.indexing import index_text_to_chroma

log = logging.getLogger("orchestrator.api.doc_db")

router = APIRouter()


def _get_config():
    from src.orchestrator.main import get_config
    return get_config()


def _get_chroma_path() -> str:
    path = os.environ.get("CHROMA_PATH", "").strip()
    if not path:
        raise ValueError("CHROMA_PATH not set")
    return path


def _get_configured_db_connections() -> list[dict]:
    """rel_db data sources for store UI; excludes app_db."""
    config = _get_config()
    return [
        {"id": ds.id, "connection_id": ds.connection_id}
        for ds in config.data_sources
        if ds.type == "rel_db" and ds.engine == "sqlite" and ds.id != "app_db"
    ]


@router.get("/doc/collections")
async def list_chroma_collections():
    """List Chroma collection names for the configured CHROMA_PATH."""
    try:
        path = _get_chroma_path()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        client = chromadb.PersistentClient(path=path)
        colls = client.list_collections()
        return {"collections": [c.name for c in colls]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/doc/upload")
async def upload_doc_to_chroma(
    file: UploadFile = File(...),
    collection_name: str = "manufacturing_docs",
):
    """Upload a text/md file, chunk, embed, and add to Chroma."""
    if not file.filename or not (
        file.filename.lower().endswith(".txt") or file.filename.lower().endswith(".md")
    ):
        raise HTTPException(status_code=400, detail="Only .txt and .md files are supported")
    try:
        path = _get_chroma_path()
        content = (await file.read()).decode("utf-8", errors="replace")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")
    if not content.strip():
        raise HTTPException(status_code=400, detail="File is empty")
    try:
        n = index_text_to_chroma(path, collection_name, content, source=file.filename or "upload")
        return {"status": "ok", "collection": collection_name, "chunks_added": n}
    except Exception as e:
        log.exception("Doc upload failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/db/connections")
async def list_db_connections():
    """List configured DB connections for the store UI."""
    return {"connections": _get_configured_db_connections()}


@router.get("/db/test")
async def test_db_connection(connection_id: str):
    """Test connection to a configured SQLite DB by connection_id (env var name)."""
    path = os.environ.get(connection_id, "").strip()
    if not path:
        raise HTTPException(
            status_code=400,
            detail=f"Connection {connection_id} not set in environment",
        )
    try:
        import aiosqlite
        async with aiosqlite.connect(path) as conn:
            await conn.execute("SELECT 1")
        return {"status": "ok", "message": "Connected"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/db/tables")
async def list_db_tables(connection_id: str):
    """List table names for a configured SQLite DB."""
    path = os.environ.get(connection_id, "").strip()
    if not path:
        raise HTTPException(
            status_code=400,
            detail=f"Connection {connection_id} not set in environment",
        )
    try:
        import aiosqlite
        async with aiosqlite.connect(path) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return {"tables": [r[0] for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
