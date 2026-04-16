"""Tests for forktex.agent.session and forktex.agent.process."""

import pytest

from forktex.agent.types import DEVELOPER, RESEARCHER, ASSISTANT
from forktex.agent.session import Session
from forktex.agent.process import AgentProcess, AgentStatus


class TestSession:
    def test_create(self):
        session = Session.create()
        assert session.id
        assert session.agent_count == 0
        assert session.is_complete is True  # No processes = complete
        assert session.root_process is None

    def test_to_dict(self):
        session = Session.create()
        d = session.to_dict()
        assert "id" in d
        assert d["agent_count"] == 0
        assert d["is_complete"] is True


class TestAgentProcess:
    def test_create(self):
        from unittest.mock import MagicMock
        loop = MagicMock()
        session = Session.create()

        process = AgentProcess.create(
            agent_type=DEVELOPER,
            session_id=session.id,
            loop=loop,
            task="test task",
        )

        assert process.id
        assert process.agent_type == DEVELOPER
        assert process.session_id == session.id
        assert process.status == AgentStatus.PENDING
        assert process.task == "test task"
        assert process.parent_id is None

    def test_to_dict(self):
        from unittest.mock import MagicMock
        loop = MagicMock()
        session = Session.create()

        process = AgentProcess.create(
            agent_type=DEVELOPER,
            session_id=session.id,
            loop=loop,
            task="build it",
        )

        d = process.to_dict()
        assert d["agent_type"] == "developer"
        assert d["status"] == "pending"
        assert d["task"] == "build it"
        assert d["result"] is None

    def test_cancel(self):
        from unittest.mock import MagicMock
        loop = MagicMock()
        session = Session.create()

        process = AgentProcess.create(
            agent_type=DEVELOPER,
            session_id=session.id,
            loop=loop,
        )

        process.cancel()
        assert process.status == AgentStatus.CANCELLED
        assert process.completed_at is not None

    def test_duration_none_before_start(self):
        from unittest.mock import MagicMock
        loop = MagicMock()
        session = Session.create()

        process = AgentProcess.create(
            agent_type=DEVELOPER,
            session_id=session.id,
            loop=loop,
        )
        assert process.duration is None

    def test_session_tracks_processes(self):
        from unittest.mock import MagicMock
        loop = MagicMock()
        session = Session.create()

        p1 = AgentProcess.create(DEVELOPER, session.id, loop)
        p2 = AgentProcess.create(RESEARCHER, session.id, loop)

        session.add_process(p1)
        session.add_process(p2)

        assert session.agent_count == 2
        assert session.root_process is p1
        assert session.is_complete is False  # Pending processes

        p1.status = AgentStatus.COMPLETED
        p2.status = AgentStatus.COMPLETED
        assert session.is_complete is True

    def test_session_get_process(self):
        from unittest.mock import MagicMock
        loop = MagicMock()
        session = Session.create()

        p1 = AgentProcess.create(DEVELOPER, session.id, loop)
        session.add_process(p1)

        assert session.get_process(p1.id) is p1
        assert session.get_process("nonexistent") is None
