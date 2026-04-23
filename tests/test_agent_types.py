"""Tests for forktex.agent.types — Agent type definitions and registry."""

import json
import pytest
from pathlib import Path

from forktex.agent.types import (
    AgentType,
    AgentTypeRegistry,
    DEVELOPER,
    RESEARCHER,
    REVIEWER,
    DEPLOYER,
    ASSISTANT,
    get_agent_type_registry,
    reset_agent_type_registry,
)


class TestAgentType:
    def test_developer_has_write_tools(self):
        assert DEVELOPER.allows_tool("write_file")
        assert DEVELOPER.allows_tool("bash_execute")
        assert DEVELOPER.allows_tool("git_commit")
        assert not DEVELOPER.allows_tool("web_search")

    def test_researcher_is_readonly_with_web(self):
        assert RESEARCHER.allows_tool("read_file")
        assert RESEARCHER.allows_tool("web_search")
        assert not RESEARCHER.allows_tool("write_file")
        assert not RESEARCHER.allows_tool("bash_execute")

    def test_reviewer_has_bash_but_no_write(self):
        assert REVIEWER.allows_tool("bash_execute")
        assert REVIEWER.allows_tool("read_file")
        assert not REVIEWER.allows_tool("write_file")

    def test_deployer_is_readonly(self):
        assert DEPLOYER.allows_tool("read_file")
        assert not DEPLOYER.allows_tool("bash_execute")
        assert not DEPLOYER.allows_tool("write_file")

    def test_assistant_allows_everything(self):
        assert ASSISTANT.allows_tool("anything")
        assert ASSISTANT.allows_tool("write_file")
        assert ASSISTANT.allows_tool("web_search")
        assert ASSISTANT.allows_tool("nonexistent_tool")

    def test_spawn_capability(self):
        assert DEVELOPER.can_spawn is True
        assert ASSISTANT.can_spawn is True
        assert RESEARCHER.can_spawn is False
        assert REVIEWER.can_spawn is False
        assert DEPLOYER.can_spawn is False

    def test_frozen(self):
        with pytest.raises(AttributeError):
            DEVELOPER.name = "hacker"


class TestAgentTypeRegistry:
    def test_builtin_types(self):
        registry = AgentTypeRegistry()
        assert "developer" in registry
        assert "researcher" in registry
        assert "reviewer" in registry
        assert "deployer" in registry
        assert "assistant" in registry
        assert "scraper" in registry
        assert len(registry) == 6

    def test_get_type(self):
        registry = AgentTypeRegistry()
        dev = registry.get("developer")
        assert dev is not None
        assert dev.name == "developer"

    def test_get_unknown_returns_none(self):
        registry = AgentTypeRegistry()
        assert registry.get("hacker") is None

    def test_list_names(self):
        registry = AgentTypeRegistry()
        names = registry.names()
        assert "developer" in names
        assert "assistant" in names

    def test_register_custom(self):
        registry = AgentTypeRegistry()
        custom = AgentType(
            name="custom",
            description="Custom agent",
            allowed_tools=frozenset({"read_file"}),
        )
        registry.register(custom)
        assert "custom" in registry
        assert registry.get("custom") is custom

    def test_load_custom_from_file(self, temp_dir):
        agents_dir = Path(temp_dir) / ".forktex" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "types.json").write_text(
            json.dumps(
                [
                    {
                        "name": "my_agent",
                        "description": "My custom agent",
                        "allowed_tools": ["read_file", "bash_execute"],
                        "can_spawn": True,
                        "system_prompt": "You are my custom agent.",
                    }
                ]
            )
        )

        registry = AgentTypeRegistry()
        registry.load_custom(temp_dir)

        assert "my_agent" in registry
        agent = registry.get("my_agent")
        assert agent.can_spawn is True
        assert agent.allows_tool("read_file")
        assert agent.allows_tool("bash_execute")
        assert not agent.allows_tool("write_file")

    def test_load_custom_missing_file(self, temp_dir):
        registry = AgentTypeRegistry()
        registry.load_custom(temp_dir)  # Should not raise
        assert len(registry) == 6  # Only built-in types

    def test_load_custom_invalid_json(self, temp_dir):
        agents_dir = Path(temp_dir) / ".forktex" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "types.json").write_text("invalid json")

        registry = AgentTypeRegistry()
        registry.load_custom(temp_dir)  # Should not raise
        assert len(registry) == 6


class TestSingleton:
    def setup_method(self):
        reset_agent_type_registry()

    def test_get_registry(self):
        r1 = get_agent_type_registry()
        r2 = get_agent_type_registry()
        assert r1 is r2

    def test_reset(self):
        r1 = get_agent_type_registry()
        reset_agent_type_registry()
        r2 = get_agent_type_registry()
        assert r1 is not r2
