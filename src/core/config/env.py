import os
from pathlib import Path

from dotenv import load_dotenv


def load_env_from_path(env_file_path: str | None, project_root: Path | None = None) -> None:
    if not env_file_path:
        return
    root = project_root or Path.cwd()
    path = root / env_file_path
    if path.exists():
        load_dotenv(path, override=False)


def get_env_vars(env_file_path: str | None = None, project_root: Path | None = None) -> dict[str, str]:
    load_env_from_path(env_file_path, project_root)
    return dict(os.environ)
