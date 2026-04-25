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

"""
forktex.agent.ui.console - Rich console helpers.
"""

from __future__ import annotations

from contextlib import contextmanager

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
        console.print("\n[bold cyan]You:[/bold cyan]")
        console.print(text)
    elif role == "assistant":
        console.print("\n[bold green]Assistant:[/bold green]")
        console.print(Markdown(text))
    elif role == "error":
        error(text)
    elif role == "info":
        info(text)
