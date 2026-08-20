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
forktex.agent.tools.base - Tool ABC, ToolResult, and ToolRegistry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel


class ToolResult(BaseModel):
    """Result of a tool execution."""

    content: str
    is_error: bool = False
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"content": self.content, "is_error": self.is_error}
        if self.data is not None:
            result["data"] = self.data
        return result


@dataclass
class Tool:
    """A callable tool with JSON schema for LLM function calling.

    Stays as a dataclass because handler is a callable (not serialisable).
    """

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    handler: Callable[..., Awaitable[ToolResult]]

    def get_schema(self) -> Dict[str, Any]:
        """Get the tool schema for LLM function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given arguments."""
        return await self.handler(**kwargs)


class ToolRegistry:
    """Registry of tools with schema generation for LLM."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_schemas(self) -> List[Dict[str, Any]]:
        """Get all tool schemas for LLM function calling."""
        return [tool.get_schema() for tool in self._tools.values()]

    async def call(self, name: str, **kwargs: Any) -> ToolResult:
        """Call a tool by name."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                content=f"Unknown tool: {name}",
                is_error=True,
            )
        try:
            return await tool.execute(**kwargs)
        except Exception as exc:
            return ToolResult(
                content=f"Tool error: {exc}",
                is_error=True,
            )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
