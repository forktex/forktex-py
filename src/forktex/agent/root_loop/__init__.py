"""Bare-``forktex`` interaction cycle.

Entry point for ``forktex`` (no subcommand). Renders a status-driven menu
that shows live auth state per facet, and auto-upgrades into the Intelligence
chat REPL when Intelligence is reachable. Menu-first today, agent-driven as
Intelligence SDK's driver module matures.
"""

from __future__ import annotations

from forktex.agent.root_loop.driver import AgentDriver, AgentResponse
from forktex.agent.root_loop.menu import run

__all__ = ["run", "AgentDriver", "AgentResponse"]
