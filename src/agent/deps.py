from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agent.worker import build_agent
from src.core.config.models import AgentConfig, DomainConfig
from src.data_access.factory import build_clients


def get_agent_config(domain_config: DomainConfig, agent_id: str) -> AgentConfig:
    agent = domain_config.get_agent_by_name(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found in config")
    return agent


def get_clients(domain_config: DomainConfig, project_root: Path | None = None) -> dict[str, Any]:
    return build_clients(domain_config, project_root)


def get_agent_runner(agent_config: AgentConfig, clients: dict[str, Any]):
    return build_agent(agent_config, clients)


# Public alias for library/serverless: build runner from (config, clients) on demand.
build_agent_runner = get_agent_runner
