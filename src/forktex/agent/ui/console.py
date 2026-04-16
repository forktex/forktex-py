"""
forktex.agent.ui.console - Rich console helpers.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def info(text: str) -> None:
    console.print(f"[dim]{text}[/dim]")


def success(text: str) -> None:
    console.print(f"[green]{text}[/green]")


def error(text: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {text}")


def warning(text: str) -> None:
    console.print(f"[yellow]Warning:[/yellow] {text}")


def panel(content: str, title: str = "", border_style: str = "cyan") -> None:
    console.print(Panel(content, title=title, border_style=border_style))


@contextmanager
def spinner(description: str = "Working..."):
    """Context manager that shows a spinner."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task(description, total=None)
        yield


def render_markdown(text: str) -> None:
    console.print(Markdown(text))


def show_message(role: str, text: str) -> None:
    """Display a chat message."""
    if role == "user":
        console.print(f"\n[bold cyan]You:[/bold cyan]")
        console.print(text)
    elif role == "assistant":
        console.print(f"\n[bold green]Assistant:[/bold green]")
        console.print(Markdown(text))
    elif role == "error":
        error(text)
    elif role == "info":
        info(text)
