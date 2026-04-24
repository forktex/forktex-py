"""forktex chat / forktex ask — Interactive chat and single-question commands.

These commands communicate with the ForkTex Intelligence API.
Conversation state is managed client-side. The Intelligence API is stateless.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import asyncclick as click
from rich.panel import Panel

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
            "Run [bold]forktex intelligence login[/bold] to set up your API endpoint and key."
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
    """Start an interactive chat session via the Intelligence API."""
    from forktex_intelligence.streams import SSEEventType
    from forktex.agent.ui.display import show_welcome, handle_tool_event

    project_root = project or _get_project_root()

    client = _build_intelligence_client(project_root)
    tool_server = _build_tool_server(project_root)
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

    # Auto-resolve org from API key
    if not client.org_id:
        try:
            await client.whoami()
        except Exception as e:
            error(f"Could not resolve org from API key: {e}")
            sys.exit(1)

    show_welcome()
    info(f"Project: {project_root}")
    info(f"Endpoint: {client._base_url}")
    info("Type your message and press Enter. Use Ctrl+C to exit.")
    info("Commands: /clear, /tools, /help")
    console.print()

    # Main REPL loop
    while True:
        try:
            user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()

            if not user_input:
                continue

            # Slash commands
            if user_input.startswith("/"):
                cmd = user_input.lower().split()[0]
                if cmd == "/clear":
                    agent_loop.conversation.clear()
                    info("Conversation cleared.")
                    continue
                elif cmd == "/tools":
                    tools = tool_server.list_tools()
                    console.print(
                        Panel(
                            "\n".join(f"  {t}" for t in tools),
                            title=f"Local Tools ({len(tools)})",
                            border_style="blue",
                        )
                    )
                    continue
                elif cmd == "/help":
                    console.print(
                        Panel(
                            "[bold]Commands:[/bold]\n\n"
                            "  /clear    Clear conversation history\n"
                            "  /tools    List available local tools\n"
                            "  /help     Show this help\n"
                            "  Ctrl+C    Exit chat",
                            title="Help",
                            border_style="blue",
                        )
                    )
                    continue
                else:
                    info(f"Unknown command: {cmd}")
                    continue

            # Stream response via agent loop (handles tool calls automatically)
            console.print(f"\n[bold green]Assistant:[/bold green]")
            full_text = ""
            try:
                async for event in agent_loop.chat_stream(user_input):
                    if event.event == SSEEventType.DELTA:
                        console.print(event.delta_text, end="")
                        full_text += event.delta_text
                    elif event.event == SSEEventType.USAGE:
                        pass  # Could display token counts
                    elif event.event == SSEEventType.ERROR:
                        error(event.error_message)
                    elif event.event == SSEEventType.DONE:
                        pass  # Stream complete for this turn (may loop for tools)
            except Exception as e:
                from forktex_intelligence.client.client import IntelligenceAPIError

                if isinstance(e, IntelligenceAPIError):
                    error(f"API error ({e.status_code}): {e.detail}")
                else:
                    error(f"Stream error: {e}")

            if full_text:
                console.print()  # Newline after streaming

        except KeyboardInterrupt:
            console.print("\n")
            break
        except EOFError:
            break

    # Cleanup
    try:
        await client.close()
    except Exception:
        pass

    console.print()
    info("Session ended.")


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
        info("Run [bold]forktex intelligence login[/bold] to configure.")
        sys.exit(1)
    except Exception as e:
        error(f"Request failed: {e}")
