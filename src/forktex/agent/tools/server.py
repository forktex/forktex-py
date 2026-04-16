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
