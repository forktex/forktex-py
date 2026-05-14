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

"""forktex.agent.types — Agent type definitions and registry.

Each AgentType defines a role with a specific tool whitelist.
Built-in types cover common development workflows.
Custom types can be loaded from .forktex/agents/types.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from forktex_cloud import paths as _cloud_paths


@dataclass(frozen=True)
class AgentType:
    """Describes a type of agent with its capabilities."""

    name: str
    description: str
    allowed_tools: frozenset[str]
    can_spawn: bool = False
    system_prompt: str = ""

    def allows_tool(self, tool_name: str) -> bool:
        """Check if this agent type is allowed to use a tool."""
        if "*" in self.allowed_tools:
            return True
        return tool_name in self.allowed_tools


# ── Built-in tool sets ──────────────────────────────────────────────────

_RO_TOOLS = frozenset(
    {
        "read_file",
        "list_directory",
        "glob_search",
        "grep_search",
        "git_status",
        "git_diff",
        "git_log",
    }
)

_RW_TOOLS = _RO_TOOLS | frozenset(
    {
        "write_file",
        "patch_file",
        "delete_file",
        "git_commit",
    }
)

_BASH_TOOLS = frozenset({"bash_execute"})
_WEB_TOOLS = frozenset({"web_search", "web_fetch"})
_DESKTOP_TOOLS = frozenset({"desktop_info", "desktop_screenshot", "desktop_observe"})

_SCRAPER_TOOLS = frozenset(
    {
        "scraper_navigate",
        "scraper_click",
        "scraper_fill",
        "scraper_select",
        "scraper_wait",
        "scraper_extract",
        "scraper_screenshot",
        "scraper_get_html",
        "scraper_evaluate",
        "scraper_truths_get",
        "scraper_truths_save",
        "scraper_save_data",
        "web_search",
    }
)

# ── Built-in agent types ────────────────────────────────────────────────

DEVELOPER = AgentType(
    name="developer",
    description="Full-access development agent with read/write, bash, and git",
    allowed_tools=_RW_TOOLS | _BASH_TOOLS | _DESKTOP_TOOLS,
    can_spawn=True,
    system_prompt=(
        "You are a development assistant. You have access to filesystem, "
        "bash, and git tools. Use them to complete the given task. "
        "Be thorough, precise, and explain what you're doing."
    ),
)

RESEARCHER = AgentType(
    name="researcher",
    description="Read-only agent with web access for research tasks",
    allowed_tools=_RO_TOOLS | _WEB_TOOLS | _DESKTOP_TOOLS,
    can_spawn=False,
    system_prompt=(
        "You are a research assistant. You can read files and search the web "
        "but cannot modify the codebase. Gather information and report findings."
    ),
)

REVIEWER = AgentType(
    name="reviewer",
    description="Read-only agent for code review with bash for running tests",
    allowed_tools=_RO_TOOLS | _BASH_TOOLS | _DESKTOP_TOOLS,
    can_spawn=False,
    system_prompt=(
        "You are a code reviewer. You can read files and run commands "
        "but cannot modify code. Review the code and provide feedback."
    ),
)

DEPLOYER = AgentType(
    name="deployer",
    description="Read-only agent for deployment verification",
    allowed_tools=_RO_TOOLS | _DESKTOP_TOOLS,
    can_spawn=False,
    system_prompt=(
        "You are a deployment assistant. You can inspect the project "
        "but cannot modify it. Verify deployment readiness."
    ),
)

ASSISTANT = AgentType(
    name="assistant",
    description="Full-access agent with all tools and spawn capability",
    allowed_tools=frozenset({"*"}),
    can_spawn=True,
    system_prompt=(
        "You are Forktex, a development assistant. You have access to all "
        "available tools. Use them to help the user with their tasks."
    ),
)

SCRAPER = AgentType(
    name="scraper",
    description="Web scraper agent with persistent browser and truths system",
    allowed_tools=_SCRAPER_TOOLS,
    can_spawn=False,
    system_prompt=(
        "You are a web scraping agent with a persistent browser. Follow these rules:\n"
        "1. ALWAYS check truths first (scraper_truths_get) for known selectors/flows.\n"
        "2. Inspect the page HTML (scraper_get_html) before clicking or extracting.\n"
        "3. IMMEDIATELY after ANY successful click, fill, select, or extract, call\n"
        "   scraper_truths_save to persist the working selector. Do NOT batch these\n"
        "   for later — save each selector the moment it works.\n"
        "4. Output structured JSON via scraper_save_data when extraction is complete.\n"
        "5. Take screenshots at key steps for debugging.\n"
        "6. If a selector fails, inspect the page and try alternatives.\n"
        "7. Use web_search to find documentation about the target site if needed.\n"
        "8. Save incremental data frequently — don't wait until the end."
    ),
)

# ── Registry ────────────────────────────────────────────────────────────

_BUILTIN_TYPES: Dict[str, AgentType] = {
    t.name: t for t in [DEVELOPER, RESEARCHER, REVIEWER, DEPLOYER, ASSISTANT, SCRAPER]
}


class AgentTypeRegistry:
    """Registry of available agent types.

    Loads built-in types and merges with custom types from
    .forktex/agents/types.json if present.
    """

    def __init__(self) -> None:
        self._types: Dict[str, AgentType] = dict(_BUILTIN_TYPES)

    def get(self, name: str) -> Optional[AgentType]:
        """Get an agent type by name."""
        return self._types.get(name)

    def list(self) -> List[AgentType]:
        """List all registered agent types."""
        return list(self._types.values())

    def names(self) -> List[str]:
        """List all registered agent type names."""
        return list(self._types.keys())

    def register(self, agent_type: AgentType) -> None:
        """Register a custom agent type."""
        self._types[agent_type.name] = agent_type

    def load_custom(self, project_root: str) -> None:
        """Load custom agent types from .forktex/agents/types.json."""
        types_file = _cloud_paths.agents_types_file(Path(project_root))
        if not types_file.exists():
            return

        try:
            data = json.loads(types_file.read_text())
            if not isinstance(data, list):
                return

            for entry in data:
                if not isinstance(entry, dict) or "name" not in entry:
                    continue

                allowed = entry.get("allowed_tools", [])
                agent_type = AgentType(
                    name=entry["name"],
                    description=entry.get("description", ""),
                    allowed_tools=frozenset(allowed),
                    can_spawn=entry.get("can_spawn", False),
                    system_prompt=entry.get("system_prompt", ""),
                )
                self._types[agent_type.name] = agent_type

        except (json.JSONDecodeError, OSError):  # fmt: skip
            pass

    def __contains__(self, name: str) -> bool:
        return name in self._types

    def __len__(self) -> int:
        return len(self._types)


# Module-level singleton
_registry: Optional[AgentTypeRegistry] = None


def get_agent_type_registry(project_root: Optional[str] = None) -> AgentTypeRegistry:
    """Get or create the agent type registry."""
    global _registry
    if _registry is None:
        _registry = AgentTypeRegistry()
        if project_root:
            _registry.load_custom(project_root)
    return _registry


def reset_agent_type_registry() -> None:
    """Reset the registry (for testing)."""
    global _registry
    _registry = None
