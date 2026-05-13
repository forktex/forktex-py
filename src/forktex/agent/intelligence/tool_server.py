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

"""Intelligence-specific ToolServer — assembles local-only tools.

This is a thin wrapper that creates the same ToolServer but only
registers tools that are safe to execute locally in the intelligence
flow (filesystem, bash, git, graph). Web tools are excluded as they
run server-side in the Intelligence API.

The bash tool can be opted out of for autonomous / unattended deployments
where giving the model arbitrary shell access is too much surface — see
``SECURITY.md §D`` and the ``enable_bash`` kwarg below.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from forktex.agent.tools.base import Tool, ToolRegistry, ToolResult
from forktex.agent.tools.bash import create_bash_tools
from forktex.agent.tools.desktop import create_desktop_tools, desktop_enabled_default
from forktex.agent.tools.filesystem import create_filesystem_tools
from forktex.agent.tools.git import create_git_tools
from forktex.agent.tools.graph_tools import create_graph_tools


_DISABLE_BASH_ENV = "FORKTEX_DISABLE_BASH"


def _bash_enabled_default() -> bool:
    """Honour the ``FORKTEX_DISABLE_BASH`` env var (any truthy value
    disables; default is enabled)."""
    return os.environ.get(_DISABLE_BASH_ENV, "").lower() not in {"1", "true", "yes"}


class ToolServer:
    """Local tool server for the intelligence agentic loop.

    Registers tools that execute on the user's machine (filesystem, bash,
    git, graph). Web and other remote-safe tools run server-side in the
    Intelligence API.

    ``enable_bash`` controls whether ``bash_execute`` is registered. The
    default follows ``FORKTEX_DISABLE_BASH``: unset / falsy → bash on,
    truthy → bash off. Pass an explicit ``True`` / ``False`` to override.
    Extra tools (e.g. scraper tools) can be injected at construction.
    """

    def __init__(
        self,
        project_root: str,
        extra_tools: Optional[List[Tool]] = None,
        *,
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

        for tool in create_filesystem_tools(project_root):
            self.registry.register(tool)
        if self.bash_enabled:
            for tool in create_bash_tools(project_root):
                self.registry.register(tool)
        for tool in create_git_tools(project_root):
            self.registry.register(tool)
        for tool in create_graph_tools(project_root):
            self.registry.register(tool)
        if self.desktop_enabled:
            for tool in create_desktop_tools(project_root):
                self.registry.register(tool)

        if extra_tools:
            for tool in extra_tools:
                self.registry.register(tool)

    async def call(self, name: str, **kwargs: Any) -> ToolResult:
        return await self.registry.call(name, **kwargs)

    def get_schemas(self) -> List[Dict[str, Any]]:
        return self.registry.list_schemas()

    def list_tools(self) -> List[str]:
        return [t.name for t in self.registry.list_tools()]

    def get_tool(self, name: str) -> Optional[Tool]:
        return self.registry.get(name)
