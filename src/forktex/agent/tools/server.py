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

"""forktex.agent.tools.server — the one ToolServer facade over the catalog.

A ``ToolServer`` composes a list of tool *groups* (from ``tools.catalog``) into
one registry and exposes ``call`` / ``get_schemas`` to the agent loop. Two named
configurations are produced by factories rather than by separate classes:

- ``local_tool_server`` — the CLI / local agent toolset (filesystem · bash · git
  · ±desktop · ±web). This is also ``ToolServer``'s zero-config default.
- ``intelligence_tool_server`` — the Intelligence-loop toolset (filesystem ·
  ±bash · git · graph · ±desktop · knowledge), with optional ``extra_tools``
  (e.g. scraper tools) injected at construction.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from forktex.agent.tools.base import Tool, ToolRegistry, ToolResult
from forktex.agent.tools.catalog import compose
from forktex.agent.tools.desktop import desktop_enabled_default

_DISABLE_BASH_ENV = "FORKTEX_DISABLE_BASH"


def _bash_enabled_default() -> bool:
    """Honour ``FORKTEX_DISABLE_BASH`` (any truthy value disables; default on)."""
    return os.environ.get(_DISABLE_BASH_ENV, "").lower() not in {"1", "true", "yes"}


class ToolServer:
    """Facade that composes tool groups into one registry for the agent loop.

    With no ``groups`` it builds the **local** toolset (filesystem · bash · git
    · ±desktop · ±web). Pass an explicit ``groups`` list (see the factories) for
    other configurations. ``bash_enabled`` follows ``FORKTEX_DISABLE_BASH``
    unless overridden; ``desktop_enabled`` follows ``desktop_enabled_default()``.
    """

    def __init__(
        self,
        project_root: str,
        extra_tools: Optional[List[Tool]] = None,
        *,
        groups: Optional[List[str]] = None,
        enable_web: bool = True,
        enable_bash: Optional[bool] = None,
        enable_desktop: Optional[bool] = None,
    ) -> None:
        self.project_root = project_root
        self.registry = ToolRegistry()
        self.bash_enabled = (
            _bash_enabled_default() if enable_bash is None else enable_bash
        )
        self.desktop_enabled = (
            desktop_enabled_default() if enable_desktop is None else enable_desktop
        )

        if groups is None:
            # Default = the local toolset. `web` degrades to [] without Playwright.
            groups = ["filesystem"]
            if self.bash_enabled:
                groups.append("bash")
            groups.append("git")
            if self.desktop_enabled:
                groups.append("desktop")
            if enable_web:
                groups.append("web")

        compose(project_root, groups, into=self.registry)

        if extra_tools:
            for tool in extra_tools:
                self.registry.register(tool)

    async def call(self, name: str, **kwargs: Any) -> ToolResult:
        """Call a tool by name."""
        return await self.registry.call(name, **kwargs)

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get all tool schemas for LLM function calling."""
        return self.registry.list_schemas()

    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return [t.name for t in self.registry.list_tools()]

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self.registry.get(name)

    def keep_only(self, predicate: Callable[[str], bool]) -> None:
        """Prune the registry in place to tools whose name passes ``predicate``.

        Used to enforce per-agent-type tool whitelists after composition.
        """
        kept = ToolRegistry()
        for tool in self.registry.list_tools():
            if predicate(tool.name):
                kept.register(tool)
        self.registry = kept


def local_tool_server(
    project_root: str,
    *,
    enable_web: bool = True,
    enable_desktop: Optional[bool] = None,
) -> ToolServer:
    """The CLI / local agent toolset (filesystem · bash · git · ±desktop · ±web)."""
    return ToolServer(
        project_root, enable_web=enable_web, enable_desktop=enable_desktop
    )


def intelligence_tool_server(
    project_root: str,
    extra_tools: Optional[List[Tool]] = None,
    *,
    enable_bash: Optional[bool] = None,
    enable_desktop: Optional[bool] = None,
) -> ToolServer:
    """The Intelligence-loop toolset (filesystem · ±bash · git · graph · ±desktop · knowledge · memory).

    Web/other remote-safe tools run server-side in the Intelligence API, so they
    are excluded here. ``knowledge`` carries the in-session recycle loop and
    degrades to [] without ``forktex-core[fractal]``.
    """
    bash_enabled = _bash_enabled_default() if enable_bash is None else enable_bash
    desktop_enabled = (
        desktop_enabled_default() if enable_desktop is None else enable_desktop
    )
    groups = ["filesystem"]
    if bash_enabled:
        groups.append("bash")
    groups += ["git", "graph"]
    if desktop_enabled:
        groups.append("desktop")
    groups += ["knowledge", "memory"]
    return ToolServer(
        project_root,
        extra_tools,
        groups=groups,
        enable_bash=enable_bash,
        enable_desktop=enable_desktop,
    )


__all__ = ["ToolServer", "local_tool_server", "intelligence_tool_server"]
