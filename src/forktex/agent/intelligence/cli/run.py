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

"""forktex run — Execute orchestrated tasks via the Intelligence API.

Uses the AgentManager to create a session and developer agent.
The Intelligence API is stateless — local tools execute on your machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console, info, error
from forktex.agent.ui.display import handle_tool_event


def _get_project_root() -> str:
    return str(Path.cwd().absolute())


@click.command()
@click.argument("task")
@click.option("--project", "-d", default=None, help="Project directory")
@click.option(
    "--agent-type",
    "-t",
    default="developer",
    help="Agent type (developer, researcher, reviewer, assistant)",
)
@click.option(
    "--desktop",
    is_flag=True,
    help="Enable observe-only desktop tools for the local agent loop.",
)
async def run(task, project, agent_type, desktop):
    """Run a task with full orchestration via the Intelligence API.

    Creates a session and agent process, then executes the task.

    Example:
        forktex run "Add error handling to src/app.py"
        forktex run --agent-type researcher "What testing patterns does this project use?"
    """
    from forktex.agent.intelligence.settings import get_intelligence_settings
    from forktex_intelligence import Intelligence
    from forktex_intelligence.streams import SSEEventType
    from forktex.agent.manager import AgentManager

    project_root = project or _get_project_root()
    settings = get_intelligence_settings(project_root=project_root)

    if not settings.is_configured:
        error("Intelligence API not configured.")
        info("Run [bold]forktex intelligence connect[/bold] to set up.")
        sys.exit(1)

    client = Intelligence.from_settings(settings)
    # Auto-resolve org from API key
    if not client.org_id:
        await client.whoami()

    manager = AgentManager(
        project_root,
        client,
        on_tool_event=handle_tool_event,
        enable_desktop=desktop,
    )

    session = manager.create_session()

    try:
        process = manager.create_agent(
            session,
            agent_type,
            task=task,
        )
    except ValueError as e:
        error(str(e))
        await client.close()
        sys.exit(1)

    try:
        console.print(f"\n[bold]Task:[/bold] {task}")
        console.print(
            f"[dim]Session: {session.id} | Agent: {process.id} ({agent_type})[/dim]"
        )
        console.print()

        # Stream the response
        console.print("[bold green]Assistant:[/bold green]")
        full_text = ""

        async for event in process.chat_stream(task):
            if event.event == SSEEventType.DELTA:
                console.print(event.delta_text, end="")
                full_text += event.delta_text
            elif event.event == SSEEventType.USAGE:
                pass
            elif event.event == SSEEventType.ERROR:
                error(event.error_message)
                break
            elif event.event == SSEEventType.DONE:
                pass

        if full_text:
            console.print()  # Newline after streaming

        # Finalize
        from forktex.agent.process import AgentStatus

        if process.status != AgentStatus.FAILED:
            process.status = AgentStatus.COMPLETED
            import time

            process.completed_at = time.time()

        manager.persist_state(process)

        console.print()
        info(f"Task completed. Agent: {process.id[:8]}...")

    except Exception as e:
        from forktex_intelligence.client.client import IntelligenceAPIError

        if isinstance(e, IntelligenceAPIError):
            error(f"API error ({e.status_code}): {e.detail}")
        else:
            error(f"Execution failed: {e}")
    finally:
        await client.close()
