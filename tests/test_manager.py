# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Tests for AgentManager — central agent orchestrator."""

import pytest
from unittest.mock import MagicMock

from forktex.agent.manager import AgentManager, MAX_SPAWN_DEPTH


@pytest.fixture
def manager(temp_dir):
    """Create an AgentManager with a mocked Intelligence client."""
    client = MagicMock()
    client.base_url = "http://test:9000"
    return AgentManager(temp_dir, client)


class TestAgentManager:
    def test_create_session(self, manager):
        session = manager.create_session()
        assert session.id is not None
        assert manager.get_session(session.id) is session

    def test_create_agent(self, manager):
        session = manager.create_session()
        process = manager.create_agent(session, "developer")
        assert process.agent_type.name == "developer"
        assert process.session_id == session.id
        assert process.parent_id is None
        assert manager.get_process(process.id) is process

    def test_create_agent_registered_in_session(self, manager):
        session = manager.create_session()
        process = manager.create_agent(session, "researcher")
        assert process in session.processes

    def test_create_agent_unknown_type(self, manager):
        session = manager.create_session()
        with pytest.raises(ValueError, match="Unknown agent type"):
            manager.create_agent(session, "nonexistent_type")

    def test_create_agent_with_task(self, manager):
        session = manager.create_session()
        process = manager.create_agent(session, "developer", task="Fix the bug")
        assert process.task == "Fix the bug"

    def test_spawn_child(self, manager):
        session = manager.create_session()
        parent = manager.create_agent(session, "developer")
        child = manager.spawn_child(parent, "researcher", "Look up docs")
        assert child.parent_id == parent.id
        assert child.task == "Look up docs"
        assert child.session_id == session.id

    def test_spawn_child_not_allowed(self, manager):
        session = manager.create_session()
        parent = manager.create_agent(session, "researcher")
        with pytest.raises(RuntimeError, match="cannot spawn"):
            manager.spawn_child(parent, "developer", "task")

    def test_spawn_depth_limit(self, manager):
        session = manager.create_session()
        # Build a chain up to MAX_SPAWN_DEPTH
        current = manager.create_agent(session, "assistant")
        for i in range(MAX_SPAWN_DEPTH):
            current = manager.spawn_child(current, "developer", f"task-{i}")

        # One more should fail
        with pytest.raises(RuntimeError, match="Max spawn depth"):
            manager.spawn_child(current, "developer", "too deep")

    def test_get_process_missing(self, manager):
        assert manager.get_process("nonexistent") is None

    def test_get_session_missing(self, manager):
        assert manager.get_session("nonexistent") is None

    def test_list_sessions(self, manager):
        s1 = manager.create_session()
        s2 = manager.create_session()
        sessions = manager.list_sessions()
        assert len(sessions) == 2
        assert {s.id for s in sessions} == {s1.id, s2.id}

    def test_list_processes(self, manager):
        session = manager.create_session()
        p1 = manager.create_agent(session, "developer")
        p2 = manager.create_agent(session, "researcher")
        processes = manager.list_processes()
        assert len(processes) == 2
        assert {p.id for p in processes} == {p1.id, p2.id}

    def test_persist_state(self, manager, temp_dir):
        session = manager.create_session()
        process = manager.create_agent(session, "developer", task="test task")
        # persist_state should not raise — it writes to .forktex/agents/history/
        manager.persist_state(process)
        # Verify the state store has the data
        history = manager._state_store.load_history(process.id)
        assert len(history) >= 1

    def test_create_agent_persists_initial_state(self, manager, temp_dir):
        session = manager.create_session()
        process = manager.create_agent(session, "developer")
        # create_agent calls save_snapshot internally
        history = manager._state_store.load_history(process.id)
        assert len(history) >= 1
        assert history[0]["agent_type"] == "developer"
