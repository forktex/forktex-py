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

"""
forktex.agent.tools.server - ToolServer assembling all tools into one facade.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from forktex.agent.tools.base import Tool, ToolRegistry, ToolResult
from forktex.agent.tools.filesystem import create_filesystem_tools
from forktex.agent.tools.bash import create_bash_tools
from forktex.agent.tools.git import create_git_tools
from forktex.agent.tools.web import create_web_tools


class ToolServer:
    """Facade that creates and registers all tools for a project.

    Single object passed through the system. Provides:
    - call(name, **kwargs) -> ToolResult
    - get_schemas() -> list of tool schemas for LLM
    """

    def __init__(self, project_root: str, enable_web: bool = True):
        self.project_root = project_root
        self.registry = ToolRegistry()

        # Register all tool groups
        for tool in create_filesystem_tools(project_root):
            self.registry.register(tool)
        for tool in create_bash_tools(project_root):
            self.registry.register(tool)
        for tool in create_git_tools(project_root):
            self.registry.register(tool)

        if enable_web:
            try:
                for tool in create_web_tools():
                    self.registry.register(tool)
            except Exception:
                pass  # Playwright not installed, skip web tools

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
