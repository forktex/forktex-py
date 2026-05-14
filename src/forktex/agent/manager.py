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

"""forktex.agent.manager — Singleton that tracks agent processes and sessions.

The AgentManager is the central coordination point for:
- Creating agent processes with the right type/tools
- Managing sessions
- Spawning child agents (hierarchical)
- Persisting state
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from forktex_intelligence import Intelligence
from forktex.agent.types import AgentType, get_agent_type_registry
from forktex.agent.process import AgentProcess
from forktex.agent.session import Session
from forktex.agent.state import AgentStateStore
from forktex.agent.intelligence.agent import LocalAgentLoop
from forktex.agent.intelligence.tool_server import ToolServer as IntelligenceToolServer
from forktex.agent.tools.server import ToolServer as FullToolServer

# Max nesting depth for hierarchical agent spawning
MAX_SPAWN_DEPTH = 3


class AgentManager:
    """Singleton that coordinates agent processes.

    Responsibilities:
    - Create agents with the correct tool whitelist based on type
    - Track sessions and their processes
    - Enable hierarchical spawning (gated by agent type)
    - Persist state for later inspection
    """

    def __init__(
        self,
        project_root: str,
        client: Intelligence,
        *,
        on_tool_event: Optional[Callable] = None,
        browser: Optional[Any] = None,
        truths_store: Optional[Any] = None,
        enable_desktop: bool = False,
    ) -> None:
        self.project_root = project_root
        self._client = client
        self._on_tool_event = on_tool_event
        self._browser = browser
        self._truths_store = truths_store
        self._enable_desktop = enable_desktop
        self._sessions: Dict[str, Session] = {}
        self._processes: Dict[str, AgentProcess] = {}
        self._state_store = AgentStateStore(project_root)
        self._type_registry = get_agent_type_registry(project_root)

    def _build_tool_server(self, agent_type: AgentType) -> IntelligenceToolServer:
        """Build a tool server filtered by agent type permissions."""
        # Inject scraper tools if browser is available and agent is a scraper
        extra_tools = None
        if (
            agent_type.name == "scraper"
            and self._browser is not None
            and self._truths_store is not None
        ):
            from forktex.agent.tools.scraper import create_scraper_tools

            extra_tools = create_scraper_tools(
                self._browser, self._truths_store, self.project_root
            )

        full_server = FullToolServer(
            self.project_root,
            enable_web=True,
            enable_desktop=self._enable_desktop,
        )

        # Register extra tools on the full server so they participate in filtering
        if extra_tools:
            for tool in extra_tools:
                full_server.registry.register(tool)

        filtered = IntelligenceToolServer.__new__(IntelligenceToolServer)
        filtered.project_root = self.project_root
        filtered.bash_enabled = "bash_execute" in agent_type.allowed_tools
        filtered.desktop_enabled = self._enable_desktop

        from forktex.agent.tools.base import ToolRegistry

        filtered.registry = ToolRegistry()

        for tool in full_server.registry.list_tools():
            if agent_type.allows_tool(tool.name):
                filtered.registry.register(tool)

        return filtered

    def create_session(self) -> Session:
        """Create a new session."""
        session = Session.create()
        self._sessions[session.id] = session
        return session

    def create_agent(
        self,
        session: Session,
        agent_type_name: str = "developer",
        *,
        system_prompt: Optional[str] = None,
        parent_id: Optional[str] = None,
        task: str = "",
    ) -> AgentProcess:
        """Create and register a new agent process."""
        agent_type = self._type_registry.get(agent_type_name)
        if agent_type is None:
            raise ValueError(f"Unknown agent type: {agent_type_name}")

        # Check spawn depth
        if parent_id:
            depth = self._get_spawn_depth(parent_id)
            if depth >= MAX_SPAWN_DEPTH:
                raise RuntimeError(f"Max spawn depth ({MAX_SPAWN_DEPTH}) exceeded")

        tool_server = self._build_tool_server(agent_type)
        system = system_prompt or agent_type.system_prompt

        loop = LocalAgentLoop(
            self._client,
            tool_server,
            system=system,
            on_tool_event=self._on_tool_event,
        )

        process = AgentProcess.create(
            agent_type=agent_type,
            session_id=session.id,
            loop=loop,
            parent_id=parent_id,
            task=task,
        )

        session.add_process(process)
        self._processes[process.id] = process

        # Persist initial state
        self._state_store.save_snapshot(process.to_dict())

        return process

    def spawn_child(
        self,
        parent: AgentProcess,
        agent_type_name: str,
        task: str,
        *,
        system_prompt: Optional[str] = None,
    ) -> AgentProcess:
        """Spawn a child agent from a parent (hierarchical spawning).

        Only allowed if the parent's type has can_spawn=True.
        """
        if not parent.agent_type.can_spawn:
            raise RuntimeError(
                f"Agent type '{parent.agent_type.name}' cannot spawn child agents"
            )

        session = self._sessions.get(parent.session_id)
        if session is None:
            raise RuntimeError(f"Session {parent.session_id} not found")

        return self.create_agent(
            session,
            agent_type_name,
            system_prompt=system_prompt,
            parent_id=parent.id,
            task=task,
        )

    def _get_spawn_depth(self, agent_id: str) -> int:
        """Calculate spawn depth by walking parent chain."""
        depth = 0
        current = agent_id
        while current:
            process = self._processes.get(current)
            if process is None or process.parent_id is None:
                break
            current = process.parent_id
            depth += 1
        return depth

    def get_process(self, agent_id: str) -> Optional[AgentProcess]:
        """Look up an agent process by ID."""
        return self._processes.get(agent_id)

    def get_session(self, session_id: str) -> Optional[Session]:
        """Look up a session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[Session]:
        """List all sessions."""
        return list(self._sessions.values())

    def list_processes(self) -> List[AgentProcess]:
        """List all agent processes."""
        return list(self._processes.values())

    def persist_state(self, process: AgentProcess) -> None:
        """Save current process state to disk."""
        self._state_store.save_snapshot(process.to_dict())
