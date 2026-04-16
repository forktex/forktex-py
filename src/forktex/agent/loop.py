"""forktex.agent.loop — Re-exports LocalAgentLoop for convenience.

The actual loop implementation lives in agent.intelligence.agent.
This module provides a shorter import path.
"""

from forktex.agent.intelligence.agent import (  # noqa: F401
    AgentResponse,
    Conversation,
    LocalAgentLoop,
    ToolEventCallback,
)
