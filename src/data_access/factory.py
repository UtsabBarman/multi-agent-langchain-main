from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.core.config.models import DomainConfig
from src.data_access.vector.chroma import create_chroma_retriever


def _load_env_for_config(config: DomainConfig, project_root: Path | None) -> dict[str, str]:
    root = project_root or Path.cwd()
    env_path = root / config.env_file_path
    if env_path.exists():
        load_dotenv(env_path, override=False)
    return dict(os.environ)


def build_clients(
    domain_config: DomainConfig,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build data access clients from domain config. Keys = data_sources[].id. SQLite + Chroma only."""
    env = _load_env_for_config(domain_config, project_root)
    clients: dict[str, Any] = {}
    root = project_root or Path.cwd()

    for ds in domain_config.data_sources:
        if ds.type == "rel_db" and ds.engine == "sqlite":
            path = env.get(ds.connection_id, "").strip()
            if not path:
                continue
            path = (root / path).resolve() if not Path(path).is_absolute() else Path(path)
            clients[ds.id] = str(path)
        elif ds.type == "vector_db" and ds.engine == "chroma":
            path = env.get(ds.connection_id, "")
            if not path:
                continue
            abs_path = (root / path).resolve() if not Path(path).is_absolute() else Path(path)
            retriever = create_chroma_retriever(
                persist_directory=str(abs_path),
                collection_name=ds.collection_name or "default",
            )
            clients[ds.id] = retriever

    return clients