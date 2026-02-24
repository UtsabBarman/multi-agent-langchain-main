import json
from pathlib import Path

from src.core.config.env import load_env_from_path
from src.core.config.models import DomainConfig
from src.core.exceptions import ConfigError


def load_domain_config(config_path: str | Path, project_root: Path | None = None) -> DomainConfig:
    root = project_root or Path.cwd()
    path = Path(config_path) if not isinstance(config_path, Path) else config_path
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {path}: {e}") from e
    try:
        config = DomainConfig.model_validate(data)
    except Exception as e:
        raise ConfigError(f"Invalid config schema in {path}: {e}") from e
    env_path = config.env_file_path
    load_env_from_path(env_path, root)
    return config
