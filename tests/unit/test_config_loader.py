"""Unit tests for config loader: file path and dict source."""
import pytest
from src.core.config.loader import load_domain_config
from src.core.config.models import DomainConfig
from src.core.exceptions import ConfigError


def test_load_domain_config_from_dict_minimal():
    """Load domain config from a dict (no file); validation uses provided env."""
    data = {
        "domain_id": "test",
        "domain_name": "Test",
        "env_file_path": ".env",
        "orchestrator": {
            "name": "orch",
            "port": 8000,
            "system_prompt": "x",
            "guardrails": [],
            "tool_names": [],
        },
        "agents": [
            {"name": "researcher", "port": 8001, "system_prompt": "x", "guardrails": [], "tool_names": []},
            {"name": "analyst", "port": 8002, "system_prompt": "x", "guardrails": [], "tool_names": []},
        ],
        "data_sources": [],
    }
    config = load_domain_config(data)
    assert isinstance(config, DomainConfig)
    assert config.domain_id == "test"
    assert len(config.agents) == 2
    assert config.get_agent_by_name("researcher").port == 8001


def test_load_domain_config_from_dict_with_env_overrides():
    """When loading from dict, env_overrides are applied for validation."""
    data = {
        "domain_id": "test",
        "domain_name": "Test",
        "env_file_path": ".env",
        "orchestrator": {"name": "orch", "port": 8000, "system_prompt": "x", "guardrails": [], "tool_names": []},
        "agents": [
            {"name": "a1", "port": 8001, "system_prompt": "x", "guardrails": [], "tool_names": []},
            {"name": "a2", "port": 8002, "system_prompt": "x", "guardrails": [], "tool_names": []},
        ],
        "data_sources": [],
    }
    config = load_domain_config(data, env_overrides={"FOO": "bar"})
    assert config.domain_id == "test"


def test_load_domain_config_invalid_dict_raises():
    """Invalid schema in dict raises ConfigError."""
    with pytest.raises(ConfigError):
        load_domain_config({"domain_id": "x"})  # missing required fields
