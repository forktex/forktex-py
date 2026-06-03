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

"""``forktex mcp`` — an MCP stdio server exposing the fractal knowledge tools.

Point an MCP client (Claude Code, Codex, …) at ``forktex mcp`` and it gets the
``knowledge_search`` / ``knowledge_show`` / ``knowledge_neighbors`` /
``knowledge_list`` tools backed by the live knowledge graph (docs principles +
project knowledge) — so the agent can pull informed constraints mid-task.
"""

from __future__ import annotations

from pathlib import Path

import asyncclick as click
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool as MCPTool

from forktex_core.fractal import FractalQuery

from forktex.agent.knowledge.sources import (
    build_knowledge_resolver,
    ensure_doc_space,
    project_doc_space,
    resolve_doc_space,
)
from forktex.agent.knowledge.tools import build_knowledge_tools

SERVER_NAME = "forktex-knowledge"
SERVER_VERSION = "0.1.0"


def build_mcp_server(
    query: FractalQuery, *, recycle_dir: str | Path | None = None
) -> Server:
    """Build an MCP server projecting the forktex knowledge tool catalog."""
    tools = {
        tool.name: tool
        for tool in build_knowledge_tools(query, recycle_dir=recycle_dir)
    }
    server: Server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list() -> list[MCPTool]:
        return [
            MCPTool(name=t.name, description=t.description, inputSchema=t.parameters)
            for t in tools.values()
        ]

    @server.call_tool()
    async def _call(name: str, arguments: dict) -> list[TextContent]:
        tool = tools.get(name)
        if tool is None:
            return [
                TextContent(type="text", text=f'{{"error": "unknown tool: {name}"}}')
            ]
        result = await tool.execute(**(arguments or {}))
        return [TextContent(type="text", text=result.content)]

    return server


async def serve_stdio(
    query: FractalQuery, *, recycle_dir: str | Path | None = None
) -> None:
    """Run the knowledge MCP server over stdio."""
    server = build_mcp_server(query, recycle_dir=recycle_dir)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


@click.command("mcp")
@click.option(
    "--docs", default=None, help="Path to the global docs repo (else $FORKTEX_DOCS)."
)
@click.option(
    "--project",
    "-d",
    default=None,
    help="Project doc-space or repo root (else ./.forktex/knowledge).",
)
@click.option(
    "--read-only",
    is_flag=True,
    default=False,
    help="Expose only read tools (no recycle).",
)
async def mcp_cmd(docs: str | None, project: str | None, read_only: bool) -> None:
    """Run an MCP server (stdio) exposing fractal knowledge tools.

    Register this with a coding agent, e.g. Claude Code:
        claude mcp add forktex -- forktex mcp

    Unless ``--read-only``, the agent can also ``knowledge_recycle`` learnings
    into the project doc-space — the shared, compounding memory across sessions.
    """
    recycle_dir = (
        None
        if read_only
        else ensure_doc_space(
            resolve_doc_space(project) if project else project_doc_space(Path.cwd())
        )
    )
    # When recycling is on, the doc-space is guaranteed to exist → it overlays,
    # so a freshly recycled node is queryable in the same session.
    resolver = build_knowledge_resolver(
        docs_path=docs, project_path=str(recycle_dir) if recycle_dir else project
    )
    await serve_stdio(FractalQuery(resolver), recycle_dir=recycle_dir)


__all__ = ["build_mcp_server", "mcp_cmd", "serve_stdio"]
