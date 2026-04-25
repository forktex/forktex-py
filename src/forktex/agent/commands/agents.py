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

"""forktex agents — Agent management CLI commands.

Commands:
    forktex agents list     List all agent processes
    forktex agents show     Show details of an agent process
    forktex agents cancel   Cancel a running agent
"""

from __future__ import annotations

import asyncclick as click

from forktex.agent.ui.console import console, info, error


@click.group()
async def agents():
    """Manage agent processes."""
    pass


@agents.command(name="list")
@click.option("--project", "-d", default=None, help="Project directory")
async def list_agents(project):
    """List all agent processes from history."""
    from pathlib import Path
    from forktex.agent.state import AgentStateStore

    project_root = project or str(Path.cwd().absolute())
    store = AgentStateStore(project_root)
    agent_ids = store.list_agents()

    if not agent_ids:
        info("No agent history found.")
        return

    console.print(f"\n[bold]Agent Processes ({len(agent_ids)}):[/bold]\n")

    for agent_id in sorted(agent_ids):
        latest = store.load_latest(agent_id)
        if latest:
            status = latest.get("status", "unknown")
            agent_type = latest.get("agent_type", "unknown")
            task = latest.get("task", "")[:60]

            status_color = {
                "completed": "green",
                "running": "yellow",
                "failed": "red",
                "cancelled": "dim",
                "pending": "blue",
            }.get(status, "white")

            console.print(
                f"  [{status_color}]{status:10}[/{status_color}] "
                f"[cyan]{agent_id}[/cyan]  "
                f"[dim]{agent_type}[/dim]  "
                f"{task}"
            )

    console.print()


@agents.command(name="show")
@click.argument("agent_id")
@click.option("--project", "-d", default=None, help="Project directory")
async def show_agent(agent_id, project):
    """Show details of an agent process."""
    from pathlib import Path
    from rich.panel import Panel
    from forktex.agent.state import AgentStateStore

    project_root = project or str(Path.cwd().absolute())
    store = AgentStateStore(project_root)

    # Support partial ID matching
    all_ids = store.list_agents()
    matches = [aid for aid in all_ids if aid.startswith(agent_id)]

    if not matches:
        error(f"No agent found matching: {agent_id}")
        return

    if len(matches) > 1:
        error(f"Ambiguous ID, matches: {', '.join(matches)}")
        return

    full_id = matches[0]
    entries = store.load_history(full_id)

    if not entries:
        error(f"No history for agent: {full_id}")
        return

    latest = entries[-1]

    lines = [
        f"[bold]ID:[/bold]         {full_id}",
        f"[bold]Type:[/bold]       {latest.get('agent_type', 'unknown')}",
        f"[bold]Status:[/bold]     {latest.get('status', 'unknown')}",
        f"[bold]Session:[/bold]    {latest.get('session_id', 'unknown')}",
        f"[bold]Parent:[/bold]     {latest.get('parent_id') or 'none'}",
        f"[bold]Task:[/bold]       {latest.get('task', '')}",
    ]

    result = latest.get("result")
    if result:
        lines.append(
            f"[bold]Tokens:[/bold]     {result.get('input_tokens', 0)} in / {result.get('output_tokens', 0)} out"
        )
        lines.append(f"[bold]Tool calls:[/bold] {result.get('tool_calls_made', 0)}")

    if latest.get("error"):
        lines.append(f"[bold red]Error:[/bold red]      {latest['error']}")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"Agent {full_id[:8]}...",
            border_style="blue",
        )
    )

    if len(entries) > 1:
        console.print(f"\n[dim]History: {len(entries)} state snapshots[/dim]")


@agents.command(name="cancel")
@click.argument("agent_id")
@click.option("--project", "-d", default=None, help="Project directory")
async def cancel_agent(agent_id, project):
    """Cancel a running agent process.

    Note: This only marks the agent as cancelled in the state store.
    It cannot interrupt a currently running agent loop.
    """
    from pathlib import Path
    from forktex.agent.state import AgentStateStore

    project_root = project or str(Path.cwd().absolute())
    store = AgentStateStore(project_root)

    all_ids = store.list_agents()
    matches = [aid for aid in all_ids if aid.startswith(agent_id)]

    if not matches:
        error(f"No agent found matching: {agent_id}")
        return

    if len(matches) > 1:
        error(f"Ambiguous ID, matches: {', '.join(matches)}")
        return

    full_id = matches[0]
    latest = store.load_latest(full_id)

    if latest and latest.get("status") in ("completed", "failed", "cancelled"):
        info(f"Agent {full_id[:8]}... already {latest['status']}")
        return

    import time

    store.append(
        full_id,
        {
            **(latest or {}),
            "status": "cancelled",
            "completed_at": time.time(),
        },
    )
    info(f"Agent {full_id[:8]}... marked as cancelled")
