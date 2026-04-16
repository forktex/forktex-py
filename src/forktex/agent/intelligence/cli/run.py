"""forktex run — Execute orchestrated tasks via the Intelligence API.

Uses the AgentManager to create a session and developer agent.
The Intelligence API is stateless — local tools execute on your machine.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import asyncclick as click

from forktex.agent.ui.console import console, info, error, spinner, render_markdown
from forktex.agent.ui.display import handle_tool_event


def _get_project_root() -> str:
    return str(Path.cwd().absolute())


@click.command()
@click.argument("task")
@click.option("--project", "-d", default=None, help="Project directory")
@click.option("--agent-type", "-t", default="developer", help="Agent type (developer, researcher, reviewer, assistant)")
async def run(task, project, agent_type):
    """Run a task with full orchestration via the Intelligence API.

    Creates a session and agent process, then executes the task.

    Example:
        forktex run "Add error handling to src/app.py"
        forktex run --agent-type researcher "What testing patterns does this project use?"
    """
    from forktex_intelligence.config import get_intelligence_settings
    from forktex_intelligence.client.client import ForktexIntelligenceClient
    from forktex_intelligence.streams import SSEEventType
    from forktex.agent.manager import AgentManager

    project_root = project or _get_project_root()
    settings = get_intelligence_settings(project_root=project_root)

    if not settings.is_configured:
        error("Intelligence API not configured.")
        info("Run [bold]forktex intelligence init[/bold] to set up.")
        sys.exit(1)

    client = ForktexIntelligenceClient.from_settings(settings)
    # Auto-resolve org from API key
    if not client._org_id:
        await client.whoami()

    manager = AgentManager(
        project_root,
        client,
        on_tool_event=handle_tool_event,
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
        console.print(f"[dim]Session: {session.id} | Agent: {process.id} ({agent_type})[/dim]")
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
        error(f"Execution failed: {e}")
    finally:
        await client.close()
