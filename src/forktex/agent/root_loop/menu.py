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

"""Menu-first root loop for bare ``forktex``.

Renders one card per service (cloud / intelligence / network) with a clear
enabled / disabled header. Input is driven by ``prompt_toolkit.PromptSession``
so arrow keys edit the line, history recall works, and a live dropdown
appears as the user types `/` (up/down to browse, Tab to accept).

Auto-upgrades into the intelligence chat REPL when intelligence is reachable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import asyncclick as click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.shortcuts import CompleteStyle
from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from forktex.agent.auth.status import collect_auth_status
from forktex.agent.auth.types import FACETS, AuthState, Facet
from forktex.agent.root_loop.slash import SERVICES, SERVICE_NAMES
from forktex.agent.ui.branding import render_logo
from forktex.agent.ui.console import console, info


_MENU_RETURN_SIGNAL = "__forktex_menu__"
_KEYS: dict[str, Facet] = {"c": "cloud", "i": "intelligence", "n": "network"}

#: Slash verbs that work from the bare menu (not only inside chat).
_MENU_SLASH = {
    "/help",
    "/status",
    "/connect",
    "/disconnect",
    "/refresh",
    "/hide",
    "/quit",
}
#: Slash verbs that only make sense inside chat — we emit a friendly redirect.
_CHAT_ONLY_SLASH = {"/tools", "/clear", "/history", "/cards", "/menu"}

#: Plain-word shortcuts accepted at the menu prompt.
_WORDS = [
    "cloud",
    "intelligence",
    "network",
    "status",
    "refresh",
    "hide",
    "quit",
    "chat",
    "help",
]


# ── input: PromptSession with live completion ────────────────────────────────


class _MenuCompleter(Completer):
    """Live completion for the menu prompt.

    Flow:
      - text starts with "/" → offer slash commands (menu-valid ones first)
        with their description as ``display_meta``.
      - text starts with "/connect " or "/disconnect " → offer the three
        services with their one-liners.
      - plain text → offer the word shortcuts (c/i/n/status/…).
    """

    def get_completions(self, document, complete_event):  # noqa: ANN001
        text = document.text_before_cursor
        # Arg-position after /connect or /disconnect.
        if text.startswith("/connect ") or text.startswith("/disconnect "):
            head, _, tail = text.partition(" ")
            service_meta = dict(SERVICES)
            for name in SERVICE_NAMES:
                if name.startswith(tail.strip()):
                    yield Completion(
                        name,
                        start_position=-len(tail.strip()),
                        display_meta=service_meta.get(name, ""),
                    )
            return
        # Slash command name position.
        if text.startswith("/"):
            from forktex.agent.root_loop.slash import SLASH_COMMANDS

            for name, cmd in SLASH_COMMANDS.items():
                if not name.startswith(text):
                    continue
                meta = cmd.description
                if name in _CHAT_ONLY_SLASH:
                    meta = f"(chat-only) {meta}"
                yield Completion(name, start_position=-len(text), display_meta=meta)
            return
        # Plain-word shortcuts.
        for w in _WORDS:
            if w.startswith(text.lower()):
                yield Completion(w, start_position=-len(text))


_session: Optional[PromptSession[str]] = None


def _get_session() -> PromptSession[str]:
    global _session
    if _session is None:
        _session = PromptSession(
            completer=_MenuCompleter(),
            complete_while_typing=True,
            complete_style=CompleteStyle.MULTI_COLUMN,
            history=InMemoryHistory(),
            mouse_support=False,
        )
    return _session


# ── loop ────────────────────────────────────────────────────────────────────


async def run(project: Optional[str] = None) -> None:
    """Entry point invoked by bare ``forktex``.

    Line-based: rich renders the cards, then ``PromptSession.prompt_async``
    takes input. The input cursor naturally follows the last printed row,
    so once the terminal fills up the prompt is pinned to the last visible
    line — that's the bottom-sticky behaviour with no layout gymnastics.
    """
    root = Path(project).resolve() if project else Path.cwd()

    states = await collect_auth_status(root, probe=True)
    hide_cards = False
    needs_render = True
    session = _get_session()

    while True:
        if needs_render and not hide_cards:
            _render_menu(states)
            needs_render = False

        intel = states["intelligence"]
        intel_ready = intel.configured and intel.reachable is True

        try:
            choice = (await session.prompt_async("> ")).strip()
        except (EOFError, KeyboardInterrupt):  # fmt: skip
            console.print("[dim]bye.[/dim]")
            return

        lc = choice.lower()

        # `forktex <service> connect|disconnect [--new]` → treat as `/connect …`.
        # Lets users paste the suggested command verbatim instead of stripping
        # the program name.
        shorthand = _parse_forktex_shorthand(lc)
        if shorthand is not None:
            slash_head, slash_args = shorthand
        else:
            slash_head = lc.split()[0] if lc.startswith("/") else ""
            slash_args = choice.split()[1:] if lc.startswith("/") else []

        if slash_head in _CHAT_ONLY_SLASH:
            info(
                f"{slash_head} is available inside chat. "
                "Press Enter (when intelligence is connected) to enter chat."
            )
            continue

        if lc in ("q", "quit", "exit") or slash_head == "/quit":
            console.print("[dim]bye.[/dim]")
            return
        if (lc in ("", "t", "chat") or slash_head == "/chat") and intel_ready:
            result = await _run_chat(str(root))
            if result == _MENU_RETURN_SIGNAL:
                needs_render = True
                continue
            return
        if lc in ("r", "refresh") or slash_head == "/refresh":
            states = await collect_auth_status(root, probe=True)
            needs_render = True
            continue
        if lc in ("h", "hide") or slash_head == "/hide":
            hide_cards = not hide_cards
            console.print(
                "[dim]cards hidden — press h to show again[/dim]"
                if hide_cards
                else "[dim]cards shown[/dim]"
            )
            needs_render = not hide_cards
            continue
        if lc in ("s", "status") or slash_head == "/status":
            from forktex.agent.auth import status_cmd

            ctx = click.get_current_context(silent=True)
            if ctx is not None:
                await ctx.invoke(
                    status_cmd, project=str(root), no_probe=False, as_json=False
                )
            continue
        if slash_head == "/help" or lc in ("?", "help"):
            _render_help()
            continue
        if slash_head in ("/connect", "/disconnect"):
            await _run_service_action(slash_head, slash_args, str(root))
            states = await collect_auth_status(root, probe=True)
            needs_render = True
            continue

        # Plain-word service drill-down.
        service = _KEYS.get(lc) or (_KEYS.get(lc[:1]) if lc else None)
        if lc in SERVICE_NAMES:
            service = lc  # type: ignore[assignment]
        if service:
            acted = await _show_service_help(
                service, states[service], str(root), session
            )
            if acted:
                states = await collect_auth_status(root, probe=True)
                needs_render = True
            continue

        if slash_head:
            info(f"unrecognised slash command: {slash_head}. try /help")
        else:
            info(f"unrecognised: {choice!r}. try /help or press h/r/s/c/i/n/q")


# ── rendering ────────────────────────────────────────────────────────────────


def _render_menu(states: dict[Facet, AuthState]) -> None:
    console.print()
    console.rule("[bold cyan]forktex[/bold cyan]", style="cyan")
    console.print()
    cards = [_card(service, states[service]) for service in FACETS]
    console.print(Columns(cards, equal=True, expand=True, padding=(0, 1)))

    hints = []
    if states["intelligence"].configured and states["intelligence"].reachable is True:
        hints.append("[green]Enter[/green] → chat")
    hints.append("[bold]c[/bold]loud")
    hints.append("[bold]i[/bold]ntelligence")
    hints.append("[bold]n[/bold]etwork")
    hints.append("[bold]s[/bold]tatus")
    hints.append("[bold]r[/bold]efresh")
    hints.append("[bold]h[/bold]ide")
    hints.append("[bold]q[/bold]uit")
    hints.append("/help")
    console.print(Panel(" · ".join(hints), border_style="dim", padding=(0, 1)))


def _card(service: Facet, state: AuthState) -> Panel:
    key = {"cloud": "c", "intelligence": "i", "network": "n"}[service]

    if not state.configured:
        header = "[bold yellow]✗ disabled[/bold yellow]"
        body = Text.from_markup(
            f"[dim]no credentials on disk[/dim]\n\n"
            f"[bold]\\[{key}][/bold] · [bold]{service}[/bold]\n\n"
            f"  connect: [cyan]forktex {service} connect[/cyan]"
        )
        border = "yellow"
    else:
        if state.reachable is True:
            header = "[bold green]✓ enabled[/bold green] · [green]reachable[/green]"
            border = "green"
        elif state.reachable is False:
            header = "[bold green]✓ enabled[/bold green] · [yellow]unreachable[/yellow]"
            border = "yellow"
        else:
            header = "[bold green]✓ enabled[/bold green]"
            border = "green"

        lines = [
            f"[bold]\\[{key}][/bold] · [bold]{service}[/bold]",
            "",
            f"endpoint:  [cyan]{state.endpoint or '—'}[/cyan]",
            f"kind:      {state.auth_kind or '—'}",
            f"scope:     {state.scope or '—'}",
        ]
        if state.principal:
            lines.append(f"principal: {_short(state.principal)}")
        for k, v in state.detail.items():
            lines.append(f"{k}: {_short(v)}")
        if state.reachable is False and state.error:
            lines.append("")
            lines.append(f"[yellow]error:[/yellow] {_short(state.error, 60)}")
        body = Text.from_markup("\n".join(lines))

    return Panel(
        Group(render_logo(service), Text(""), body),
        title=header,
        border_style=border,
        padding=(0, 1),
    )


def _short(s: str, limit: int = 28) -> str:
    s = str(s)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _render_help() -> None:
    """Help panel — organised into four scannable sections.

    Style convention: ``Ctrl+R`` / ``Ctrl+Shift+R`` (capitalised verb after
    the plus). Letter-key shortcuts are shown lowercase (`c`, `h`, `q`).
    """
    rows: list[tuple[str, str, str]] = [
        # single-keystroke shortcuts at the prompt
        ("shortcuts", "c  /  i  /  n", "drill into cloud / intelligence / network"),
        ("shortcuts", "s", "aggregate status table"),
        ("shortcuts", "r", "refresh probes (re-ping all services)"),
        ("shortcuts", "h", "hide / show the service cards"),
        ("shortcuts", "q", "quit"),
        ("shortcuts", "Enter", "enter chat  (intelligence must be reachable)"),
        ("shortcuts", "?  /  /help", "this list"),
        # prompt_toolkit's built-in emacs-style line-editing keys
        ("line editing", "↑  /  ↓", "previous / next command from history"),
        ("line editing", "Ctrl+R", "reverse search through history"),
        ("line editing", "Ctrl+S", "forward search through history"),
        ("line editing", "Ctrl+A  /  Ctrl+E", "jump to start / end of line"),
        ("line editing", "Ctrl+W", "delete word backwards"),
        ("line editing", "Ctrl+U", "delete whole line"),
        ("line editing", "Ctrl+K", "delete to end of line"),
        ("line editing", "Ctrl+L", "clear screen"),
        ("line editing", "Tab", "autocomplete  (type / to see slash commands)"),
        ("line editing", "Ctrl+C  /  Ctrl+D", "abort / exit"),
        # slash commands valid at the menu prompt
        ("slash commands", "/help", "this list"),
        ("slash commands", "/status", "aggregate credential state"),
        (
            "slash commands",
            "/connect <service> [--new]",
            "connect (idempotent login-or-register)",
        ),
        ("slash commands", "/disconnect <service>", "remove saved credentials"),
        ("slash commands", "/refresh", "same as r"),
        ("slash commands", "/hide", "same as h"),
        ("slash commands", "/quit", "same as q"),
        (
            "slash commands",
            "/tools /clear /history /cards /menu",
            "chat-only — available after Enter → chat",
        ),
    ]
    lines = ["[bold]forktex menu[/bold]"]
    group = ""
    for kind, key, desc in rows:
        if kind != group:
            lines.append(f"\n[dim]── {kind} ──[/dim]")
            group = kind
        lines.append(f"  [cyan]{key:<38}[/cyan] {desc}")
    lines.append("")
    lines.append("[dim]── services ──[/dim]")
    for name, desc in SERVICES:
        lines.append(f"  [cyan]{name:<38}[/cyan] {desc}")
    lines.append("")
    lines.append(
        "[dim]Tip:[/dim] paste a full command verbatim — e.g. "
        "[cyan]forktex cloud connect[/cyan] — and it runs as [cyan]/connect cloud[/cyan]."
    )
    console.print("\n".join(lines))


async def _run_service_action(
    slash_head: str, args: list[str], project_root: str
) -> None:
    # Parse `[--new] <service>` for /connect.
    new_account = False
    service: Optional[str] = None
    for a in args:
        if a == "--new":
            new_account = True
        elif service is None:
            service = a.lower()

    if not service:
        info(
            f"usage: {slash_head} <{' | '.join(SERVICE_NAMES)}>{' [--new]' if slash_head == '/connect' else ''}"
        )
        return
    if service not in SERVICE_NAMES:
        info(f"unknown service: {service}. must be one of {', '.join(SERVICE_NAMES)}")
        return

    if slash_head == "/disconnect":
        from forktex.agent.auth.store import clear as store_clear

        path = store_clear(service, "global", None)  # type: ignore[arg-type]
        console.print(f"[green]✓[/green] disconnected from {service} @ global: {path}")
        return

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
    try:
        await impls[service](
            project=project_root,
            save_global=False,
            endpoint=None,
            email=None,
            password=None,
            api_key=None,
            new_account=new_account,
        )
    except SystemExit:
        # _render_connect_error already emitted the diagnostic panel.
        pass
    except Exception as exc:
        info(f"{slash_head} failed: {exc}")


def _parse_forktex_shorthand(lc: str) -> Optional[tuple[str, list[str]]]:
    """Translate `forktex <service> connect|disconnect [--new]` (verbatim
    shell paste) into a `(slash_head, args)` tuple the main loop understands.
    """
    parts = lc.split()
    if len(parts) < 3 or parts[0] != "forktex":
        return None
    service = parts[1]
    verb = parts[2]
    if service not in SERVICE_NAMES or verb not in ("connect", "disconnect"):
        return None
    return f"/{verb}", [service] + parts[3:]


async def _show_service_help(
    service: Facet,
    state: AuthState,
    project_root: str,
    session: PromptSession[str],
) -> bool:
    """Show status for *service*; offer an inline connect if not configured.

    Returns True if an action was taken (and the menu should re-render).
    """
    if state.configured:
        console.print(
            f"[bold]{service}[/bold] is configured at [cyan]{state.endpoint}[/cyan] "
            f"(scope: {state.scope})."
        )
        console.print(f"  → `forktex {service} connect` to re-capture credentials")
        console.print(f"  → `forktex {service} disconnect` to remove them")
        console.print(f"  → `forktex {service} status` for health check")
        return False

    console.print(f"[bold]{service}[/bold] is not configured.")
    try:
        answer = (
            (
                await session.prompt_async(
                    "  connect now? [Y/n] ",
                    default="y",
                )
            )
            .strip()
            .lower()
        )
    except (EOFError, KeyboardInterrupt):  # fmt: skip
        return False
    if answer and answer not in ("y", "yes", ""):
        console.print("[dim]dismissed.[/dim]")
        return False
    await _run_service_action("/connect", [service], project_root)
    return True


async def _run_chat(project_root: str) -> Optional[str]:
    """Hand off to the existing intelligence chat REPL."""
    from forktex.agent.intelligence.cli.chat import chat as chat_cmd

    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return None
    try:
        await ctx.invoke(chat_cmd, project=project_root)
    except SystemExit:
        return None
    return None
