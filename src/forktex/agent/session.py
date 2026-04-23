"""forktex.agent.session — Groups agents from one CLI invocation.

A session represents a single user interaction (e.g., `forktex run "..."`)
and tracks all agent processes spawned during that interaction.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from forktex.core.utils import generate_id
from forktex.agent.process import AgentProcess, AgentStatus


@dataclass
class Session:
    """Groups agent processes from one CLI invocation."""

    id: str
    created_at: float = field(default_factory=time.time)
    processes: List[AgentProcess] = field(default_factory=list)

    @classmethod
    def create(cls) -> Session:
        return cls(id=generate_id())

    def add_process(self, process: AgentProcess) -> None:
        """Track an agent process in this session."""
        self.processes.append(process)

    @property
    def root_process(self) -> Optional[AgentProcess]:
        """The first (root) agent process in this session."""
        return self.processes[0] if self.processes else None

    @property
    def is_complete(self) -> bool:
        """True if all processes have finished."""
        if not self.processes:
            return True
        return all(
            p.status
            in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED)
            for p in self.processes
        )

    @property
    def agent_count(self) -> int:
        return len(self.processes)

    def get_process(self, agent_id: str) -> Optional[AgentProcess]:
        """Find a process by ID."""
        for p in self.processes:
            if p.id == agent_id:
                return p
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "agent_count": self.agent_count,
            "is_complete": self.is_complete,
            "processes": [p.to_dict() for p in self.processes],
        }
