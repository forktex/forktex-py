"""
forktex.agent.ui.display - Session info, usage display, progress.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from forktex.agent.ui.console import console, info


CLI_VERSION = "0.5.0"

# Max characters to show for tool argument values and results
_ARG_TRUNCATE = 120
_RESULT_TRUNCATE = 300


def show_welcome() -> None:
    console.print(Panel.fit(
        "[bold cyan]Forktex[/bold cyan] - AI-Powered Development Assistant\n"
        f"Version {CLI_VERSION}",
        border_style="cyan",
    ))


def show_session_info(model: str, project_root: str) -> None:
    info(f"Project: {project_root}")
    info(f"Model: {model}")
    console.print()


def show_usage_summary(tracker: Any) -> None:
    """Display usage summary from tracker."""
    console.print(f"[dim]{tracker.format_display()}[/dim]")


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "..."


def show_tool_call(name: str, args: Dict[str, Any]) -> None:
    """Display a tool call being made, with formatted arguments."""
    console.print()
    console.print(f"  [bold yellow]Tool Call:[/bold yellow] [bold]{name}[/bold]")
    for key, value in args.items():
        val_str = repr(value) if not isinstance(value, str) else value
        val_str = _truncate(val_str, _ARG_TRUNCATE)
        # Indent multi-line values
        lines = val_str.splitlines()
        if len(lines) > 1:
            console.print(f"    [cyan]{key}:[/cyan]")
            for line in lines[:10]:
                console.print(f"      {line}")
            if len(lines) > 10:
                console.print(f"      [dim]... ({len(lines) - 10} more lines)[/dim]")
        else:
            console.print(f"    [cyan]{key}:[/cyan] {val_str}")


def show_tool_result(name: str, content: str, is_error: bool = False) -> None:
    """Display tool result with truncation."""
    label_style = "bold red" if is_error else "bold green"
    label = "Error" if is_error else "Result"
    truncated = _truncate(content, _RESULT_TRUNCATE)

    lines = truncated.splitlines()
    if len(lines) <= 1:
        console.print(f"  [{label_style}]{label}:[/{label_style}] {truncated}")
    else:
        console.print(f"  [{label_style}]{label}:[/{label_style}]")
        for line in lines[:15]:
            console.print(f"    {line}")
        if len(lines) > 15:
            console.print(f"    [dim]... ({len(lines) - 15} more lines)[/dim]")
    console.print()


def handle_tool_event(event: str, tool_name: str, data: Dict[str, Any]) -> None:
    """Unified handler for tool events from the DeveloperAgent callback."""
    if event == "call":
        show_tool_call(tool_name, data)
    elif event == "result":
        show_tool_result(tool_name, data.get("content", ""), data.get("is_error", False))
