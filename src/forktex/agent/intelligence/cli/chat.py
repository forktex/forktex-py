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
    """Create an Intelligence client from persisted settings.

    forktex-py owns FS persistence (resolves env + project + global
    config files); the SDK is consumed via its constructor only.
    """
    from forktex.agent.intelligence.settings import get_intelligence_settings
    from forktex_intelligence import Intelligence

    settings = get_intelligence_settings(project_root=project_root)
    if not settings.is_configured:
        error("Intelligence API not configured.")
        info(
            "Run [bold]forktex intelligence connect[/bold] to set up your API endpoint and key."
        )
        sys.exit(1)
    return Intelligence(endpoint=settings.endpoint, api_key=settings.api_key)


def _build_tool_server(project_root: str, *, enable_desktop: bool = False):
    """Create the intelligence-loop tool server for tool intercepts."""
    from forktex.agent.tools.server import intelligence_tool_server

    return intelligence_tool_server(project_root, enable_desktop=enable_desktop)


def _build_agent_loop(client, tool_server, system=None, on_tool_event=None):
    """Create the agent loop with client-side conversation management."""
    from forktex.agent.engine import AgentLoop
    from forktex.agent.intelligence.provider import IntelligenceProvider

    return AgentLoop(
        IntelligenceProvider(client),
        tool_server,
        system=system,
        on_tool_event=on_tool_event,
    )


@click.command()
@click.option("--project", "-d", default=None, help="Project directory")
@click.option(
    "--desktop",
    is_flag=True,
    help="Enable observe-only desktop tools for the local agent loop.",
)
@click.option(
    "--workspace",
    is_flag=True,
    help="Ground on the whole workspace: resolve the workspace root (the "
    "parent dir holding your repos) so the agent loads its `docs/AGENTS.md` "
    "+ the cross-project knowledge graph, for cross-cutting questions.",
)
async def chat(project, desktop, workspace):
    """Start an interactive chat session via the Intelligence API.

    Layout is driven by `prompt_toolkit`: input pinned at the bottom, slash
    commands autocomplete on Tab, service cards toggle with `Ctrl+K`.
    See `forktex/agent/root_loop/chat_app.py` for the layout code.

    With ``--workspace`` the agent grounds on the workspace root instead of
    the current project — best for "how does X flow across the platforms?".
    """
    await start_chat_session(project=project, desktop=desktop, workspace=workspace)


def _resolve_chat_root(project: Optional[str], workspace: bool) -> str:
    """Resolve the project root to ground on (workspace root when ``workspace``)."""
    if project or not workspace:
        return project or _get_project_root()

    from forktex.core.paths import find_workspace_root

    eco_root = find_workspace_root(Path.cwd())
    if eco_root:
        info(f"Workspace grounding: [cyan]{eco_root}[/cyan]")
        return str(eco_root)
    error("No workspace root found above cwd — grounding on the project.")
    return _get_project_root()


def _build_chat_runtime(project_root: str, *, desktop: bool = False):
    """Wire the client, tool server, and grounded agent loop for a chat session."""
    from forktex.agent.ui.display import handle_tool_event
    from forktex.agent.intelligence.grounding import build_system_prompt

    client = _build_intelligence_client(project_root)
    tool_server = _build_tool_server(project_root, enable_desktop=desktop)
    # Grounded system prompt: persona + AGENTS.md + cached manual@agents bundle
    # (if `forktex arch build` has run); falls back to the persona alone.
    agent_loop = _build_agent_loop(
        client,
        tool_server,
        system=build_system_prompt(project_root),
        on_tool_event=handle_tool_event,
    )
    return client, tool_server, agent_loop


async def start_chat_session(
    *,
    project: Optional[str] = None,
    desktop: bool = False,
    workspace: bool = False,
    initial_message: Optional[str] = None,
) -> None:
    """Build the chat app and run it.

    Shared entry point for the ``forktex chat`` Click command and the
    bare-``forktex`` menu's free-form-text route. The ``initial_message``
    arg (when set) is auto-submitted as the first user turn — that's
    how typing free-form text at the menu becomes the opening turn of
    a chat session.

    ``workspace=True`` (no explicit ``project``) resolves the workspace
    root via :func:`find_workspace_root` and grounds there — the existing
    grounding then injects the workspace ``docs/AGENTS.md`` + the composed
    cross-project knowledge graph (this is what the retired ``agents root``
    command did, minus its dead architecture-snapshot loaders).
    """
    project_root = _resolve_chat_root(project, workspace)
    client, tool_server, agent_loop = _build_chat_runtime(project_root, desktop=desktop)

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
        await run_chat(
            agent_loop,
            tool_server,
            project_root,
            seed_welcome=seed,
            initial_message=initial_message,
        )
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
    from forktex_intelligence import Inputs

    project_root = project or _get_project_root()

    try:
        from forktex.agent.intelligence.settings import get_intelligence_settings

        settings = get_intelligence_settings(project_root=project_root)
        if not getattr(settings, "is_configured", False):
            error("Intelligence API not configured.")
            info("Run [bold]forktex intelligence connect[/bold] to set up.")
            sys.exit(1)

        async with Intelligence(
            endpoint=settings.endpoint, api_key=settings.api_key
        ) as ai:
            with spinner("Thinking..."):
                model = await ai.find_model(destination="chat")
                if model is None:
                    error("No chat-capable model available in the catalog.")
                    sys.exit(1)
                out = await ai.invoke(model, Inputs.user(prompt))

            if out.text:
                console.print()
                console.print("[bold green]Assistant:[/bold green]")
                render_markdown(out.text)
            else:
                error("Empty response from Intelligence API")

            usage = out.usage
            if usage is not None and getattr(usage, "totalTokens", 0):
                info(f"Tokens: {usage.inputTokens} in / {usage.outputTokens} out")

    except RuntimeError as e:
        error(str(e))
        info("Run [bold]forktex intelligence connect[/bold] to configure.")
        sys.exit(1)
    except Exception as e:
        error(f"Request failed: {e}")
