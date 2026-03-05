from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env_from_path(env_file_path: Optional[str], project_root: Optional[Path] = None) -> None:
    if not env_file_path:
        return
    root = project_root or Path.cwd()
    path = root / env_file_path
    if path.exists():
        load_dotenv(path, override=False)


def get_env_vars(env_file_path: Optional[str] = None, project_root: Optional[Path] = None) -> dict:
    load_env_from_path(env_file_path, project_root)
    return dict(os.environ)
