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

"""Slash-command registry for the chat REPL (and reused by the menu).

One source of truth for command names, descriptions, and handlers — used by
the hint bar, the Tab/live completer, and `/help`.

Handlers receive a ``SlashContext`` with references to the chat app state,
the agent loop, and a way to push status lines into the scroll buffer.
They may be sync or async; the dispatcher awaits when appropriate.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Union

HandlerResult = Union[None, str]  # optional status-line to emit
Handler = Callable[
    ["SlashContext", list[str]], Union[HandlerResult, Awaitable[HandlerResult]]
]


# ── the three services (single source of truth — reused by completers & help) ─

SERVICES: list[tuple[str, str]] = [
    ("cloud", "deploy + manage infrastructure (controller + org credentials)"),
    ("intelligence", "AI agent + tools (API key, chat, ask, run)"),
    ("network", "identity, projects, tasks, worklogs (JWT)"),
]

SERVICE_NAMES: list[str] = [name for name, _ in SERVICES]


def service_description(name: str) -> str:
    return dict(SERVICES).get(name, "")


@dataclass
class SlashCommand:
    name: str
    description: str
    handler: Handler
    arg_completer: Optional[Callable[[], list[str]]] = None  # e.g. service names


@dataclass
class SlashContext:
    """Shared state the slash handlers act on."""

    app_state: Any  # ChatAppState — avoid circular import via Any
    agent_loop: Any  # LocalAgentLoop
    tool_server: Any  # ToolServer
    project_root: str
    emit: Callable[[str], None]  # push a pre-formatted string into the scroll buffer
    emit_markup: Callable[[str], None]  # same, but renders rich markup
    exit_signal: Callable[
        [str], None
    ]  # request app exit with a reason ("quit" | "menu")


# ── handlers ─────────────────────────────────────────────────────────────────


def _cmd_help(ctx: SlashContext, args: list[str]) -> str:
    lines = ["[bold]slash commands[/bold]", ""]
    for cmd in SLASH_COMMANDS.values():
        lines.append(f"  [cyan]{cmd.name:<14}[/cyan] {cmd.description}")
    lines.append("")
    lines.append("[bold]services[/bold]  (targets for /connect and /disconnect)")
    for name, desc in SERVICES:
        lines.append(f"  [cyan]{name:<14}[/cyan] {desc}")
    lines.append("")
    lines.append("[bold]keybindings[/bold]")
    lines.append("  [cyan]Ctrl+K[/cyan]         toggle service cards")
    lines.append("  [cyan]Ctrl+H[/cyan]         show full transcript")
    lines.append("  [cyan]Ctrl+L[/cyan]         clear visible buffer")
    lines.append("  [cyan]Ctrl+D[/cyan]  /  [cyan]Ctrl+C[/cyan]   exit to menu")
    lines.append("  [cyan]Tab[/cyan]            autocomplete")
    ctx.emit_markup("\n".join(lines))
    return None


def _cmd_cards(ctx: SlashContext, args: list[str]) -> str:
    ctx.app_state.show_cards = not ctx.app_state.show_cards
    return f"cards: {'shown' if ctx.app_state.show_cards else 'hidden'}"


async def _cmd_status(ctx: SlashContext, args: list[str]) -> str:
    from forktex.agent.auth.status import collect_auth_status

    states = await collect_auth_status(ctx.project_root, probe=True)
    lines = ["[bold]status[/bold]"]
    for name, s in states.items():
        if not s.configured:
            lines.append(f"  [yellow]✗[/yellow] {name}  not configured")
            continue
        state = (
            "reachable"
            if s.reachable
            else ("unreachable" if s.reachable is False else "configured")
        )
        lines.append(
            f"  [green]✓[/green] {name:<13} {state:<13} [cyan]{s.endpoint}[/cyan]"
        )
    ctx.emit_markup("\n".join(lines))
    return None


async def _cmd_connect(ctx: SlashContext, args: list[str]) -> str:
    # Parse `[--new] <service>` in either order for convenience.
    new_account = False
    service: Optional[str] = None
    for a in args:
        if a == "--new":
            new_account = True
        elif service is None:
            service = a.lower()
    if not service:
        return f"usage: /connect <{' | '.join(SERVICE_NAMES)}> [--new]"
    if service not in SERVICE_NAMES:
        return f"unknown service: {service}. must be one of {', '.join(SERVICE_NAMES)}"

    from forktex.agent.auth.cli import (
        connect_cloud,
        connect_intelligence,
        connect_network,
    )

    impls = {
        "cloud": connect_cloud,
        "intelligence": connect_intelligence,
        "network": connect_network,
    }
    impl = impls[service]

    # login impls prompt via rich.Prompt.ask; detach prompt_toolkit I/O for the turn.
    from prompt_toolkit.application import get_app

    app = get_app()
    try:
        with app.input.detach():
            with app.output.detach():
                await impl(
                    project=ctx.project_root,
                    save_global=False,
                    endpoint=None,
                    email=None,
                    password=None,
                    api_key=None,
                    new_account=new_account,
                )
    except SystemExit:
        # _render_connect_error already printed the details; no extra line.
        return None
    except Exception as exc:
        return f"connect failed: {exc}"

    ctx.app_state.show_cards = True
    ctx.app_state.flash_cards_until = __import__("time").monotonic() + 3.0
    return f"✓ connected to {service}"


def _cmd_disconnect(ctx: SlashContext, args: list[str]) -> str:
    if not args:
        return f"usage: /disconnect <{' | '.join(SERVICE_NAMES)}>"
    service = args[0].lower()
    if service not in SERVICE_NAMES:
        return f"unknown service: {service}. must be one of {', '.join(SERVICE_NAMES)}"

    from forktex.agent.auth.store import clear as store_clear

    path = store_clear(service, "global", None)  # type: ignore[arg-type]
    return f"disconnected from {service} → {path}"


def _cmd_clear(ctx: SlashContext, args: list[str]) -> None:
    ctx.app_state.buffer.text = ""
    return None


def _cmd_history(ctx: SlashContext, args: list[str]) -> str:
    ctx.emit_markup("[dim]— transcript —[/dim]")
    for m in ctx.app_state.transcript:
        ctx.emit(m)
    return None


def _cmd_tools(ctx: SlashContext, args: list[str]) -> str:
    tools = ctx.tool_server.list_tools()
    lines = [f"[bold]local tools ({len(tools)})[/bold]"]
    for t in tools:
        lines.append(f"  {t}")
    ctx.emit_markup("\n".join(lines))
    return None


def _cmd_menu(ctx: SlashContext, args: list[str]) -> str:
    ctx.exit_signal("menu")
    return "returning to menu"


def _cmd_quit(ctx: SlashContext, args: list[str]) -> str:
    ctx.exit_signal("quit")
    return "bye."


# ── registry ─────────────────────────────────────────────────────────────────


def _services() -> list[str]:
    return SERVICE_NAMES


SLASH_COMMANDS: dict[str, SlashCommand] = {
    "/help": SlashCommand("/help", "show this list", _cmd_help),
    "/status": SlashCommand("/status", "show service state", _cmd_status),
    "/cards": SlashCommand("/cards", "toggle service cards", _cmd_cards),
    "/connect": SlashCommand(
        "/connect", "connect <service> [--new]", _cmd_connect, _services
    ),
    "/disconnect": SlashCommand(
        "/disconnect", "disconnect <service>", _cmd_disconnect, _services
    ),
    "/clear": SlashCommand("/clear", "clear visible buffer", _cmd_clear),
    "/history": SlashCommand("/history", "show full transcript", _cmd_history),
    "/tools": SlashCommand("/tools", "list local tool-server tools", _cmd_tools),
    "/menu": SlashCommand("/menu", "exit chat to bare menu", _cmd_menu),
    "/quit": SlashCommand("/quit", "exit forktex", _cmd_quit),
}


async def dispatch(ctx: SlashContext, line: str) -> Optional[str]:
    """Run a slash command. Returns an optional status line to emit."""
    parts = line.strip().split()
    if not parts:
        return None
    name = parts[0].lower()
    if name not in SLASH_COMMANDS:
        return f"unknown slash command: {name}. try /help"
    cmd = SLASH_COMMANDS[name]
    result = cmd.handler(ctx, parts[1:])
    if inspect.isawaitable(result):
        result = await result
    return result
