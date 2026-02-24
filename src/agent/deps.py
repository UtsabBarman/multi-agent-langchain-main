from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.core.config.loader import load_domain_config
from src.core.config.models import AgentConfig, DomainConfig
from src.data_access.factory import build_clients
from src.agent.worker import build_agent


def get_agent_config(domain_config: DomainConfig, agent_id: str) -> AgentConfig:
    agent = domain_config.get_agent_by_name(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found in config")
    return agent


def get_clients(domain_config: DomainConfig, project_root: Path | None = None) -> dict[str, Any]:
    return build_clients(domain_config, project_root)


def get_agent_runner(agent_config: AgentConfig, clients: dict[str, Any]):
    return build_agent(agent_config, clients)
