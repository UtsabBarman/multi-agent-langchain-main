"""Unit tests for AgentConfig.base_url and DomainConfig.get_agent_base_url."""
from src.core.config.models import AgentConfig, DomainConfig


def test_get_agent_base_url_uses_port_when_no_base_url():
    """When agent has no base_url, URL is http://host:port."""
    config = DomainConfig(
        domain_id="test",
        domain_name="Test",
        env_file_path=".env",
        orchestrator=AgentConfig(name="o", port=8000, system_prompt="x", guardrails=[], tool_names=[]),
        agents=[
            AgentConfig(name="researcher", port=8001, system_prompt="x", guardrails=[], tool_names=[]),
        ],
        data_sources=[],
    )
    assert config.get_agent_base_url("researcher") == "http://127.0.0.1:8001"
    assert config.get_agent_base_url("researcher", host="agent") == "http://agent:8001"


def test_get_agent_base_url_uses_base_url_when_set():
    """When agent has base_url, that is returned (trailing slash stripped)."""
    config = DomainConfig(
        domain_id="test",
        domain_name="Test",
        env_file_path=".env",
        orchestrator=AgentConfig(name="o", port=8000, system_prompt="x", guardrails=[], tool_names=[]),
        agents=[
            AgentConfig(
                name="researcher",
                port=8001,
                system_prompt="x",
                guardrails=[],
                tool_names=[],
                base_url="https://my-func.azurewebsites.net/api/researcher",
            ),
        ],
        data_sources=[],
    )
    assert config.get_agent_base_url("researcher") == "https://my-func.azurewebsites.net/api/researcher"
    assert config.get_agent_base_url("researcher", host="ignored") == "https://my-func.azurewebsites.net/api/researcher"


def test_get_agent_base_url_strips_trailing_slash():
    """base_url with trailing slash is returned without it."""
    config = DomainConfig(
        domain_id="test",
        domain_name="Test",
        env_file_path=".env",
        orchestrator=AgentConfig(name="o", port=8000, system_prompt="x", guardrails=[], tool_names=[]),
        agents=[
            AgentConfig(
                name="researcher",
                port=8001,
                system_prompt="x",
                guardrails=[],
                tool_names=[],
                base_url="https://example.com/agent/",
            ),
        ],
        data_sources=[],
    )
    assert config.get_agent_base_url("researcher") == "https://example.com/agent"
