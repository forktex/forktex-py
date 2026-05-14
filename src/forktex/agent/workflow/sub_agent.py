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

"""Sub-agent typed contracts + spawn entry point.

A *sub-agent* is a focused, bounded execution that runs with a curated
tool subset and a constrained budget (turns + wall-clock). The parent
agent decides what to delegate; the spawn helper handles the rest.

Phase A delivers the **typed contracts** + a stub ``spawn_sub_agent``
that validates inputs and raises ``NotImplementedError`` at the
execution boundary. Phase B will wire the existing ``AgentManager``
scaffolding at ``forktex.agent.manager`` to actually run the loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from forktex.intelligence.protocol import Intelligence


__all__ = [
    "Artifact",
    "ArtifactKind",
    "SubAgentResult",
    "SubAgentSpec",
    "SubAgentStatus",
    "spawn_sub_agent",
]


SubAgentStatus = Literal["completed", "failed", "timeout", "cancelled"]
ArtifactKind = Literal["file_change", "captured_output", "tool_result", "summary"]


# Default tool subsets curated for common specialist roles. The plan-mode
# loop can pass these to ``SubAgentSpec.tool_subset`` rather than spelling
# every tool name out. Keep these tight — sub-agents misbehave when given
# every tool the parent has.
_RESEARCHER_TOOLS = frozenset(
    {
        "read_file",
        "list_directory",
        "glob_search",
        "grep_search",
        "graph_summary",
        "list_packages",
        "find_package",
        "find_modules",
        "package_imports",
        "find_importers",
    }
)
_EDITOR_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "patch_file",
        "delete_file",
        "list_directory",
        "glob_search",
        "grep_search",
    }
)
_AUDITOR_TOOLS = frozenset(
    {
        "read_file",
        "list_directory",
        "glob_search",
        "grep_search",
        "git_status",
        "git_diff",
        "git_log",
        "graph_summary",
        "fsd_status",
    }
)

DEFAULT_TOOL_SUBSETS: dict[str, frozenset[str]] = {
    "researcher": _RESEARCHER_TOOLS,
    "editor": _EDITOR_TOOLS,
    "auditor": _AUDITOR_TOOLS,
}


@dataclass(frozen=True)
class SubAgentSpec:
    """Configuration for spawning a sub-agent.

    The parent agent picks the role (researcher / editor / auditor /
    custom), the intent, and the budget. The defaults are conservative —
    sub-agents should fail fast rather than run forever.
    """

    name: str
    intent: str
    tool_subset: frozenset[str]
    system_prompt_addendum: str = ""
    max_rounds: int = 5
    timeout_s: float = 60.0

    def __post_init__(self) -> None:
        if self.max_rounds < 1:
            raise ValueError(
                f"SubAgentSpec.max_rounds must be >= 1; got {self.max_rounds}"
            )
        if self.timeout_s <= 0:
            raise ValueError(
                f"SubAgentSpec.timeout_s must be > 0; got {self.timeout_s}"
            )
        if not self.name:
            raise ValueError("SubAgentSpec.name must be non-empty")
        if not self.intent:
            raise ValueError("SubAgentSpec.intent must be non-empty")

    @classmethod
    def for_role(
        cls,
        role: str,
        intent: str,
        *,
        name: str | None = None,
        max_rounds: int = 5,
        timeout_s: float = 60.0,
        system_prompt_addendum: str = "",
    ) -> SubAgentSpec:
        """Build a spec from a predefined role (researcher / editor / auditor)."""
        if role not in DEFAULT_TOOL_SUBSETS:
            raise ValueError(
                f"unknown sub-agent role {role!r}; "
                f"expected one of {sorted(DEFAULT_TOOL_SUBSETS)}"
            )
        return cls(
            name=name or role,
            intent=intent,
            tool_subset=DEFAULT_TOOL_SUBSETS[role],
            system_prompt_addendum=system_prompt_addendum,
            max_rounds=max_rounds,
            timeout_s=timeout_s,
        )


@dataclass(frozen=True)
class Artifact:
    """A concrete output produced by a sub-agent.

    Stays narrow — a sub-agent's contribution to the parent's context
    should be a small set of typed artifacts the parent can fold into
    its own state, not a free-form blob.
    """

    kind: ArtifactKind
    summary: str  # one-line description for the parent's context
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubAgentResult:
    """Outcome of a sub-agent run."""

    name: str
    status: SubAgentStatus
    summary: str  # the parent reads this; keep it short and load-bearing
    artifacts: tuple[Artifact, ...] = ()
    tokens_used: int = 0
    rounds_used: int = 0
    error: str | None = None  # populated when status != "completed"


async def spawn_sub_agent(
    spec: SubAgentSpec,
    *,
    parent_intelligence: "Intelligence",
    parent_tool_server: Any,  # forktex.agent.intelligence.tool_server.ToolServer
) -> SubAgentResult:
    """Spawn a sub-agent with the given spec, return its result.

    Phase A delivers the **contract** — input validation, types, error
    boundaries. Phase B wires the actual execution loop via
    ``forktex.agent.manager.AgentManager``.

    Raises ``NotImplementedError`` until Phase B lands, so any caller
    accidentally invoking this in Phase A surfaces a clear failure
    instead of silently no-op'ing.
    """
    # Validate the parent surfaces are present — fail fast in Phase A so
    # callers can't pass garbage and get a confusing error in Phase B.
    if parent_intelligence is None:
        raise ValueError("spawn_sub_agent requires a parent Intelligence")
    if parent_tool_server is None:
        raise ValueError("spawn_sub_agent requires a parent ToolServer")
    # Tool-subset gating: every tool the sub-agent asks for must exist
    # in the parent's tool server.
    available = _available_tools(parent_tool_server)
    missing = spec.tool_subset - available
    if missing:
        raise ValueError(
            f"sub-agent {spec.name!r} requests tools not on parent server: "
            f"{sorted(missing)}"
        )
    raise NotImplementedError(
        "spawn_sub_agent execution lands in Phase B via "
        "forktex.agent.manager.AgentManager. The Phase A contract above "
        "is the stable surface; an implementation can plug in without "
        "API change."
    )


def _available_tools(tool_server: Any) -> frozenset[str]:
    """Best-effort: pull the set of tool names from a ToolServer."""
    # ToolServer.get_schemas() returns list[dict] with a 'name' key.
    get_schemas = getattr(tool_server, "get_schemas", None)
    if not callable(get_schemas):
        return frozenset()
    try:
        schemas = get_schemas()
    except Exception:
        return frozenset()
    return frozenset(
        str(s["name"]) for s in schemas if isinstance(s, dict) and "name" in s
    )
