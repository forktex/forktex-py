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

"""forktex chat / forktex ask — Interactive chat and single-question commands.

These commands communicate with the ForkTex Intelligence API.
Conversation state is managed client-side. The Intelligence API is stateless.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import asyncclick as click

from forktex.agent.ui.console import console, info, error, spinner, render_markdown


def _get_project_root() -> str:
    return str(Path.cwd().absolute())


def _build_intelligence_client(project_root: Optional[str] = None):
    """Create Intelligence API client from settings."""
    from forktex.agent.intelligence.settings import get_intelligence_settings
    from forktex_intelligence.client.client import ForktexIntelligenceClient

    settings = get_intelligence_settings(project_root=project_root)

    if not settings.is_configured:
        error("Intelligence API not configured.")
        info(
            "Run [bold]forktex intelligence connect[/bold] to set up your API endpoint and key."
        )
        sys.exit(1)

    return ForktexIntelligenceClient.from_settings(settings)


def _build_tool_server(project_root: str):
    """Create the local tool server for tool intercepts."""
    from forktex.agent.intelligence.tool_server import ToolServer

    return ToolServer(project_root)


def _build_agent_loop(client, tool_server, system=None, on_tool_event=None):
    """Create the local agent loop with client-side conversation management."""
    from forktex.agent.intelligence.agent import LocalAgentLoop

    return LocalAgentLoop(
        client,
        tool_server,
        system=system,
        on_tool_event=on_tool_event,
    )


@click.command()
@click.option("--project", "-d", default=None, help="Project directory")
async def chat(project):
    """Start an interactive chat session via the Intelligence API.

    Layout is driven by `prompt_toolkit`: input pinned at the bottom, slash
    commands autocomplete on Tab, service cards toggle with `Ctrl+K`.
    See `forktex/agent/root_loop/chat_app.py` for the layout code.
    """
    project_root = project or _get_project_root()

    client = _build_intelligence_client(project_root)
    tool_server = _build_tool_server(project_root)

    from forktex.agent.ui.display import handle_tool_event

    agent_loop = _build_agent_loop(
        client,
        tool_server,
        system=(
            "You are Forktex, a development assistant. You have access to local tools "
            "for reading/writing files, running bash commands, and git operations. "
            "Use them to help the user with their development tasks."
        ),
        on_tool_event=handle_tool_event,
    )

    # Auto-resolve org from API key (network-bound; do it before entering the app).
    if not client.org_id:
        try:
            await client.whoami()
        except Exception as e:
            error(f"Could not resolve org from API key: {e}")
            sys.exit(1)

    from forktex.agent.root_loop.chat_app import run_chat

    seed = (
        f"forktex chat\n"
        f"endpoint: {client._base_url}\n"
        f"project:  {project_root}\n"
        f"press /help or Tab for commands · Ctrl+D exits\n"
    )

    try:
        await run_chat(agent_loop, tool_server, project_root, seed_welcome=seed)
    finally:
        try:
            await client.close()
        except Exception:
            pass


@click.command()
@click.argument("prompt")
@click.option("--project", "-d", default=None, help="Project directory")
async def ask(prompt, project):
    """Ask a single question via the Intelligence API.

    Example:
        forktex ask "What files are in this project?"
    """
    from forktex.intelligence import Intelligence

    project_root = project or _get_project_root()

    try:
        async with Intelligence(project_root=project_root) as ai:
            with spinner("Thinking..."):
                response = await ai.chat(prompt)

            if response.text:
                console.print()
                console.print("[bold green]Assistant:[/bold green]")
                render_markdown(response.text)
            else:
                error("Empty response from Intelligence API")

            if response.total_tokens:
                info(
                    f"Tokens: {response.input_tokens} in / {response.output_tokens} out"
                )

    except RuntimeError as e:
        error(str(e))
        info("Run [bold]forktex intelligence connect[/bold] to configure.")
        sys.exit(1)
    except Exception as e:
        error(f"Request failed: {e}")
