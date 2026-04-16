"""Intelligence-specific ToolServer — assembles local-only tools.

This is a thin wrapper that creates the same ToolServer but only
registers tools that are safe to execute locally in the intelligence
flow (filesystem, bash, git). Web tools are excluded as they
run server-side in the Intelligence API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from forktex.agent.tools.base import Tool, ToolRegistry, ToolResult
from forktex.agent.tools.filesystem import create_filesystem_tools
from forktex.agent.tools.bash import create_bash_tools
from forktex.agent.tools.git import create_git_tools


class ToolServer:
    """Local tool server for the intelligence agentic loop.

    Only registers tools that execute on the user's machine:
    filesystem, bash, git. Web and other remote-safe tools
    run server-side in the Intelligence API.

    Extra tools (e.g. scraper tools) can be injected at construction.
    """

    def __init__(
        self,
        project_root: str,
        extra_tools: Optional[List[Tool]] = None,
    ) -> None:
        self.project_root = project_root
        self.registry = ToolRegistry()

        for tool in create_filesystem_tools(project_root):
            self.registry.register(tool)
        for tool in create_bash_tools(project_root):
            self.registry.register(tool)
        for tool in create_git_tools(project_root):
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
