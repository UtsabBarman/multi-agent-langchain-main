"""Domain config validation: fail fast on startup."""
from __future__ import annotations

import os

from src.core.config.models import DomainConfig
from src.core.exceptions import ConfigError


def validate_domain_config(config: DomainConfig, env: dict[str, str] | None = None) -> None:
    """Validate domain config: port uniqueness, tool availability, schema compatibility.
    Raises ConfigError on first failure. Use env to check data_source connection_id vars (default: os.environ).
    """
    env = env if env is not None else dict(os.environ)

    # 1. Port uniqueness
    ports: list[tuple[str, int]] = []
    ports.append((config.orchestrator.name, config.orchestrator.port))
    for a in config.agents:
        ports.append((a.name, a.port))
    seen: dict[int, str] = {}
    for name, port in ports:
        if port in seen:
            raise ConfigError(
                f"Duplicate port {port}: used by both '{seen[port]}' and '{name}'. "
                "Ensure orchestrator and all agents have unique ports."
            )
        seen[port] = name

    # 2. Tool names: every agent's tool_names must be in the registry
    from src.tools.registry import get_registered_tool_names
    known_tool_names = frozenset(get_registered_tool_names())
    seen_agents: set[str] = set()
    for agent in config.agents:
        if agent.name in seen_agents:
            raise ConfigError(f"Duplicate agent name '{agent.name}' in config.agents.")
        seen_agents.add(agent.name)
        for tool_name in agent.tool_names:
            if tool_name not in known_tool_names:
                raise ConfigError(
                    f"Agent '{agent.name}' references unknown tool '{tool_name}'. "
                    f"Available tools: {sorted(known_tool_names)}."
                )

    # 3. Data source shape: enforce supported combinations.
    for ds in config.data_sources:
        supported = (ds.type == "rel_db" and ds.engine == "sqlite") or (
            ds.type == "vector_db" and ds.engine == "chroma"
        )
        if not supported:
            raise ConfigError(
                f"Unsupported data source '{ds.id}': type='{ds.type}', engine='{ds.engine}'."
            )

    # 4. Data sources: warn if connection_id env var is not set (optional backends like Chroma may be unset)
    import logging
    _log = logging.getLogger("config.validation")
    for ds in config.data_sources:
        val = env.get(ds.connection_id)
        if not val or not str(val).strip():
            _log.warning(
                "Data source '%s' expects env var '%s' to be set; tools using it may be no-ops.",
                ds.id,
                ds.connection_id,
            )
