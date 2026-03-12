from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.core.config.env import load_env_from_path
from src.core.config.models import DomainConfig
from src.core.exceptions import ConfigError
from src.data_access.vector.chroma import create_chroma_retriever


def _load_env_for_config(config: DomainConfig, project_root: Path | None) -> dict[str, str]:
    load_env_from_path(config.env_file_path, project_root)
    return dict(os.environ)


def build_clients(
    domain_config: DomainConfig,
    project_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build data access clients from domain config. Keys = data_sources[].id. SQLite + Chroma only.

    If env is provided, use it and do not load from config's env file (for serverless/library).
    If env is None, load env from config's env_file_path relative to project_root (default).
    """
    if env is not None:
        env = dict(env)
    else:
        env = _load_env_for_config(domain_config, project_root)
    clients: dict[str, Any] = {}
    root = project_root or Path.cwd()

    for ds in domain_config.data_sources:
        if ds.type == "rel_db" and ds.engine == "sqlite":
            path = env.get(ds.connection_id, "").strip()
            if not path:
                continue
            abs_path = (root / path).resolve() if not Path(path).is_absolute() else Path(path)
            clients[ds.id] = str(abs_path)
        elif ds.type == "vector_db" and ds.engine == "chroma":
            path = env.get(ds.connection_id, "")
            if not path:
                continue
            abs_path = (root / path).resolve() if not Path(path).is_absolute() else Path(path)
            collection_name = ds.collection_name or "default"
            retriever = create_chroma_retriever(
                persist_directory=str(abs_path),
                collection_name=collection_name,
            )
            clients[ds.id] = retriever
            clients[f"{ds.id}_index"] = {"path": str(abs_path), "collection_name": collection_name}
        else:
            raise ConfigError(
                f"Unsupported data source '{ds.id}': type='{ds.type}', engine='{ds.engine}'."
            )

    return clients