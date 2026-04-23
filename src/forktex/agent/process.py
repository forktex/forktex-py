"""forktex.agent.process — AgentProcess wraps a LocalAgentLoop with identity and state.

Each AgentProcess has a unique ID, type, status, and optional parent.
It delegates actual work to LocalAgentLoop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from forktex.core.utils import generate_id
from forktex.agent.types import AgentType
from forktex.agent.intelligence.agent import LocalAgentLoop, AgentResponse
from forktex_intelligence.streams import SSEEvent


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentProcess:
    """An agent process with identity, type, and lifecycle management.

    Wraps a LocalAgentLoop and adds:
    - Unique ID
    - Agent type (determines tool access)
    - Status tracking
    - Parent-child relationships
    - Timing metadata
    """

    id: str
    agent_type: AgentType
    session_id: str
    parent_id: Optional[str] = None
    status: AgentStatus = AgentStatus.PENDING
    task: str = ""
    result: Optional[AgentResponse] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    _loop: Optional[LocalAgentLoop] = field(default=None, repr=False)

    @classmethod
    def create(
        cls,
        agent_type: AgentType,
        session_id: str,
        loop: LocalAgentLoop,
        *,
        parent_id: Optional[str] = None,
        task: str = "",
    ) -> AgentProcess:
        """Create a new agent process."""
        return cls(
            id=generate_id(),
            agent_type=agent_type,
            session_id=session_id,
            parent_id=parent_id,
            task=task,
            _loop=loop,
        )

    async def chat_stream(self, content: str) -> AsyncIterator[SSEEvent]:
        """Stream a chat response through the agent loop."""
        if self._loop is None:
            raise RuntimeError("Agent process has no loop attached")

        self.status = AgentStatus.RUNNING
        if self.started_at is None:
            self.started_at = time.time()

        try:
            async for event in self._loop.chat_stream(content):
                yield event
        except Exception as e:
            self.status = AgentStatus.FAILED
            self.error = str(e)
            raise

    async def run_task(self, task: str) -> AgentResponse:
        """Execute a task and return the accumulated response."""
        if self._loop is None:
            raise RuntimeError("Agent process has no loop attached")

        self.task = task
        self.status = AgentStatus.RUNNING
        self.started_at = time.time()

        try:
            response = await self._loop.run_task(task)
            self.result = response
            self.status = AgentStatus.COMPLETED
            self.completed_at = time.time()

            if response.error:
                self.status = AgentStatus.FAILED
                self.error = response.error

            return response
        except Exception as e:
            self.status = AgentStatus.FAILED
            self.error = str(e)
            self.completed_at = time.time()
            raise

    def cancel(self) -> None:
        """Cancel the agent process."""
        self.status = AgentStatus.CANCELLED
        self.completed_at = time.time()

    @property
    def duration(self) -> Optional[float]:
        """Duration in seconds, or None if not started."""
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for persistence."""
        return {
            "id": self.id,
            "agent_type": self.agent_type.name,
            "session_id": self.session_id,
            "parent_id": self.parent_id,
            "status": self.status.value,
            "task": self.task,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result": {
                "text": self.result.text,
                "tool_calls_made": len(self.result.tool_calls_made),
                "input_tokens": self.result.input_tokens,
                "output_tokens": self.result.output_tokens,
            }
            if self.result
            else None,
        }
