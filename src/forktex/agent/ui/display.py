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
forktex.agent.ui.display - Session info, usage display, progress.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from rich.panel import Panel

from forktex import __version__ as _BASE_VERSION
from forktex.agent.ui.branding import render_row
from forktex.agent.ui.console import console, info

# Append a `(dev-linked)` suffix when the user has explicitly opted into
# sibling-SDK editable installs via `make dev-link-sdks`. The env flag is a
# courtesy signal — it does not influence import resolution.
CLI_VERSION = (
    f"{_BASE_VERSION} (dev-linked)"
    if os.environ.get("FORKTEX_DEV_SIBLING_SDKS")
    else _BASE_VERSION
)

# Max characters to show for tool argument values and results
_ARG_TRUNCATE = 120
_RESULT_TRUNCATE = 300


def show_welcome() -> None:
    console.print(render_row(["cloud", "intelligence", "network"]))
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Forktex[/bold cyan] - AI-Powered Development Assistant\n"
            f"Version {CLI_VERSION}",
            border_style="cyan",
        )
    )


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
        show_tool_result(
            tool_name, data.get("content", ""), data.get("is_error", False)
        )
