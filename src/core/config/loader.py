"""Load domain config from file path or dict (library-friendly, pluggable source)."""
import json
import os
from pathlib import Path
from typing import Any

from src.core.config.env import load_env_from_path
from src.core.config.models import DomainConfig
from src.core.config.validation import validate_domain_config
from src.core.exceptions import ConfigError


def load_domain_config(
    config_path: str | Path | dict[str, Any],
    project_root: Path | None = None,
    env_overrides: dict[str, str] | None = None,
) -> DomainConfig:
    """Load and validate domain config from a file path or a dict.

    - If config_path is a path (str or Path): read JSON from file, load env from
      config's env_file_path (relative to project_root), validate. Use for local runs.
    - If config_path is a dict: validate only; do not load env from file. Caller
      must set env (e.g. os.environ or env_overrides). Use for tests and serverless.

    env_overrides: optional env vars to apply (e.g. for library callers). Applied
      after loading from file when config_path is a path; when config_path is a dict,
      only env_overrides and current os.environ are used for validation (no file load).
    """
    root = project_root or Path.cwd()
    if isinstance(config_path, dict):
        data = config_path
        env = dict(os.environ)
        if env_overrides:
            env.update(env_overrides)
        try:
            config = DomainConfig.model_validate(data)
        except Exception as e:
            raise ConfigError(f"Invalid config schema: {e}") from e
        validate_domain_config(config, env=env)
        return config

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
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    validate_domain_config(config, env=env)
    return config
