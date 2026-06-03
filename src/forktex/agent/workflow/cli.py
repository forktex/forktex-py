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

"""forktex plan — craft a multi-step plan and execute it across agents.

forktex drafts a structured plan from the task, shows it, and (after approval)
executes the steps — delegating to specialist sub-agents — via the in-process
executor (or the durable ``@flow`` tier when a flow DB is configured).
"""

from __future__ import annotations

import sys
from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console, error, info
from forktex.agent.ui.display import handle_tool_event


def _summarize_step(step) -> str:
    from forktex.agent.workflow.plan import (
        FileEditStep,
        ShellStep,
        SubAgentStep,
        ToolCallStep,
    )

    p = step.payload
    if isinstance(p, SubAgentStep):
        return f"sub_agent[{p.spec_name}] — {p.spec_intent}"
    if isinstance(p, ToolCallStep):
        return f"tool_call {p.tool}({', '.join(p.arguments)})"
    if isinstance(p, ShellStep):
        return f"shell: {p.command}"
    if isinstance(p, FileEditStep):
        return f"file_edit {p.operation}: {p.path}"
    return step.kind


def _render_plan(plan) -> None:
    console.print(f"\n[bold]Intent:[/bold] {plan.intent}")
    console.print(f"[dim]{plan.rationale}[/dim]\n")
    console.print("[bold]Steps:[/bold]")
    for i, step in enumerate(plan.steps, 1):
        console.print(f"  {i}. {_summarize_step(step)}")
    console.print(f"\n[bold]Expected outcome:[/bold] {plan.expected_outcome}\n")


@click.command()
@click.argument("task")
@click.option("--project", "-d", default=None, help="Project directory")
@click.option("--yes", "-y", is_flag=True, help="Execute without confirmation")
@click.option("--desktop", is_flag=True, help="Enable observe-only desktop tools.")
async def plan(task, project, yes, desktop):
    """Craft a multi-agent plan for TASK and execute it.

    forktex drafts the plan, shows it, and on approval runs the steps —
    delegating to researcher/editor/auditor sub-agents as needed.

    Example:
        forktex plan "Find where retries are configured, then document it"
    """
    from forktex.agent.intelligence.settings import get_intelligence_settings
    from forktex_intelligence import Intelligence
    from forktex.agent.tools.server import intelligence_tool_server
    from forktex.agent.workflow.craft import craft_plan
    from forktex.agent.workflow.executor import select_executor

    project_root = project or str(Path.cwd().absolute())
    settings = get_intelligence_settings(project_root=project_root)
    if not settings.is_configured:
        error("Intelligence API not configured. Run: forktex intelligence connect")
        sys.exit(1)

    client = Intelligence.from_settings(settings)
    if not client.org_id:
        await client.whoami()

    try:
        console.print(f"[bold]Task:[/bold] {task}")
        with console.status("[cyan]crafting plan…[/cyan]", spinner="dots"):
            plan_obj = await craft_plan(task, intelligence=client, project_root=project_root)
        _render_plan(plan_obj)

        if plan_obj.requires_approval and not yes:
            if not click.confirm("Execute this plan?", default=False):
                info("Aborted — no changes made.")
                return

        tool_server = intelligence_tool_server(project_root, enable_desktop=desktop)
        executor = select_executor(client, tool_server, on_tool_event=handle_tool_event)

        console.print("[bold green]Executing:[/bold green]")
        result = await executor.execute(
            plan_obj,
            on_step_event=lambda kind, name, data: console.print(f"[dim]▸ {name}[/dim]"),
        )

        console.print()
        for i, sr in enumerate(result.steps, 1):
            mark = "[green]✓[/green]" if sr.status == "completed" else "[red]✗[/red]"
            console.print(f"  {mark} {i}. {sr.kind} — {sr.summary or sr.error or ''}".rstrip())
        console.print()
        if result.status == "completed":
            info(f"Plan completed — {len(result.steps)} step(s).")
        else:
            error(
                f"Plan failed at step {(result.failed_index or 0) + 1}. "
                + (f"Rollback hint: {result.rollback_hint}" if result.rollback_hint else "")
            )

    except Exception as e:
        from forktex_intelligence import IntelligenceAPIError

        if isinstance(e, IntelligenceAPIError):
            error(f"API error ({e.status_code}): {e.detail}")
        else:
            error(f"Plan failed: {e}")
    finally:
        await client.close()
