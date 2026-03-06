from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Standard locations for .env (first existing wins)
_PROJECT_ENV_PATHS = ("config/env/.env", ".env")


def ensure_project_env(project_root: Optional[Path] = None) -> None:
    """Load .env from project (config/env/.env then .env). Use in app/script entrypoints."""
    root = project_root or Path.cwd()
    for name in _PROJECT_ENV_PATHS:
        path = root / name
        if path.exists():
            load_dotenv(path, override=False)
            return


def load_env_from_path(env_file_path: Optional[str], project_root: Optional[Path] = None) -> None:
    """Load env from a given path (e.g. from domain config)."""
    if not env_file_path:
        return
    root = project_root or Path.cwd()
    path = root / env_file_path
    if path.exists():
        load_dotenv(path, override=False)


def get_env_vars(env_file_path: Optional[str] = None, project_root: Optional[Path] = None) -> dict:
    """Return current env; optionally load from path first."""
    load_env_from_path(env_file_path, project_root)
    return dict(os.environ)
