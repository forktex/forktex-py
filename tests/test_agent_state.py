"""Tests for forktex.agent.state — Agent state persistence."""

import json
import pytest
from pathlib import Path

from forktex.agent.state import AgentStateStore


class TestAgentStateStore:
    def test_append_and_load(self, temp_dir):
        store = AgentStateStore(temp_dir)
        store.append("agent-1", {"status": "pending", "task": "test"})
        store.append("agent-1", {"status": "running", "task": "test"})

        entries = store.load_history("agent-1")
        assert len(entries) == 2
        assert entries[0]["status"] == "pending"
        assert entries[1]["status"] == "running"

    def test_load_latest(self, temp_dir):
        store = AgentStateStore(temp_dir)
        store.append("agent-1", {"status": "pending"})
        store.append("agent-1", {"status": "completed"})

        latest = store.load_latest("agent-1")
        assert latest is not None
        assert latest["status"] == "completed"

    def test_load_nonexistent(self, temp_dir):
        store = AgentStateStore(temp_dir)
        assert store.load_history("nope") == []
        assert store.load_latest("nope") is None

    def test_list_agents(self, temp_dir):
        store = AgentStateStore(temp_dir)
        store.append("agent-1", {"status": "pending"})
        store.append("agent-2", {"status": "running"})

        agents = store.list_agents()
        assert "agent-1" in agents
        assert "agent-2" in agents

    def test_list_empty(self, temp_dir):
        store = AgentStateStore(temp_dir)
        assert store.list_agents() == []

    def test_delete(self, temp_dir):
        store = AgentStateStore(temp_dir)
        store.append("agent-1", {"status": "done"})
        assert "agent-1" in store.list_agents()

        store.delete("agent-1")
        assert "agent-1" not in store.list_agents()

    def test_save_snapshot(self, temp_dir):
        store = AgentStateStore(temp_dir)
        store.save_snapshot(
            {
                "id": "abc123",
                "status": "completed",
                "agent_type": "developer",
                "task": "build something",
            }
        )

        latest = store.load_latest("abc123")
        assert latest is not None
        assert latest["agent_type"] == "developer"
