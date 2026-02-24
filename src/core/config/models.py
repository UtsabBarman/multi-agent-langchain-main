from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    name: str
    port: int
    system_prompt: str
    guardrails: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    chat_history_path: str | None = None  # JSON file for this agent's chat history; default data/chat/{name}.json

    def get_chat_history_path(self, project_root: Any = None) -> str:
        """Resolved path for this agent's chat history JSON (relative to project root)."""
        if self.chat_history_path:
            return self.chat_history_path
        return f"data/chat/{self.name}.json"


class DataSourceConfig(BaseModel):
    id: str
    type: str  # "rel_db" | "vector_db"
    engine: str  # "postgres" | "chroma"
    connection_id: str  # env var name
    collection_name: str | None = None  # for chroma


class SessionStoreConfig(BaseModel):
    type: str  # "postgres"
    connection_id: str


class DomainConfig(BaseModel):
    domain_id: str
    domain_name: str
    env_file_path: str
    orchestrator: AgentConfig  # same signature as agents (name, port, system_prompt, guardrails, tool_names)
    agents: list[AgentConfig] = Field(default_factory=list)
    data_sources: list[DataSourceConfig] = Field(default_factory=list)
    session_store: SessionStoreConfig | None = None

    def get_agent_by_name(self, name: str) -> AgentConfig | None:
        for a in self.agents:
            if a.name == name:
                return a
        return None

    def get_agent_base_url(self, name: str, host: str = "127.0.0.1") -> str:
        agent = self.get_agent_by_name(name)
        if not agent:
            raise ValueError(f"Agent {name} not in config")
        return f"http://{host}:{agent.port}"
