"""Menu-first root loop for bare ``forktex``.

Renders one card per facet with a clear enabled / disabled header, then
auto-upgrades into the intelligence chat REPL when intelligence is reachable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import asyncclick as click
from rich.columns import Columns
from rich.panel import Panel
from rich.text import Text

from forktex.agent.auth.status import collect_auth_status
from forktex.agent.auth.types import FACETS, AuthState, Facet
from forktex.agent.ui.console import console, info


_MENU_RETURN_SIGNAL = "__forktex_menu__"
_KEYS: dict[str, Facet] = {"c": "cloud", "i": "intelligence", "n": "network"}


async def run(project: Optional[str] = None) -> None:
    """Entry point invoked by bare ``forktex``."""
    root = Path(project).resolve() if project else Path.cwd()

    while True:
        states = await collect_auth_status(root, probe=True)
        _render_menu(states)

        intel = states["intelligence"]
        intel_ready = intel.configured and intel.reachable is True

        choice = (await _prompt_choice(intel_ready=intel_ready)).strip().lower()

        if choice in ("q", "quit", "exit"):
            console.print("[dim]bye.[/dim]")
            return
        if choice in ("", "t", "chat") and intel_ready:
            result = await _run_chat(str(root))
            if result == _MENU_RETURN_SIGNAL:
                continue
            return
        if choice in ("s", "status"):
            from forktex.agent.auth import status_cmd

            ctx = click.get_current_context(silent=True)
            if ctx is not None:
                await ctx.invoke(status_cmd, project=str(root), no_probe=False, as_json=False)
            continue
        facet = _KEYS.get(choice) or _KEYS.get(choice[:1]) if choice else None
        if facet:
            _show_facet_help(facet, states[facet])
            continue
        info(f"unrecognised: {choice!r}")


def _render_menu(states: dict[Facet, AuthState]) -> None:
    console.print()
    console.rule("[bold cyan]forktex[/bold cyan]", style="cyan")
    console.print()
    cards = [_card(facet, states[facet]) for facet in FACETS]
    console.print(Columns(cards, equal=True, expand=True, padding=(0, 1)))

    hints = []
    if states["intelligence"].configured and states["intelligence"].reachable is True:
        hints.append("[green]Enter[/green] → chat")
    hints.append("[bold]c[/bold]loud")
    hints.append("[bold]i[/bold]ntelligence")
    hints.append("[bold]n[/bold]etwork")
    hints.append("[bold]s[/bold]tatus")
    hints.append("[bold]q[/bold]uit")
    console.print(Panel(" · ".join(hints), border_style="dim", padding=(0, 1)))


def _card(facet: Facet, state: AuthState) -> Panel:
    key = {"cloud": "c", "intelligence": "i", "network": "n"}[facet]

    if not state.configured:
        header = "[bold yellow]✗ disabled[/bold yellow]"
        body = Text.from_markup(
            f"[dim]no credentials on disk[/dim]\n\n"
            f"[bold]\\[{key}][/bold] · [bold]{facet}[/bold]\n\n"
            f"  login:  [cyan]forktex {facet} login[/cyan]"
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
            f"[bold]\\[{key}][/bold] · [bold]{facet}[/bold]",
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

    return Panel(body, title=header, border_style=border, padding=(0, 1))


def _short(s: str, limit: int = 28) -> str:
    s = str(s)
    return s if len(s) <= limit else s[: limit - 1] + "…"


async def _prompt_choice(intel_ready: bool) -> str:
    default = "t" if intel_ready else "s"
    try:
        return await click.prompt(">", default=default, show_default=False, prompt_suffix=" ")
    except (click.exceptions.Abort, EOFError, KeyboardInterrupt):
        return "q"


def _show_facet_help(facet: Facet, state: AuthState) -> None:
    if state.configured:
        console.print(
            f"[bold]{facet}[/bold] is configured at [cyan]{state.endpoint}[/cyan] "
            f"(scope: {state.scope})."
        )
        console.print(f"  → `forktex {facet} login` to re-capture")
        console.print(f"  → `forktex {facet} logout` to remove")
        console.print(f"  → `forktex {facet} status` for health check")
    else:
        console.print(f"[bold]{facet}[/bold] is not configured.")
        console.print(f"  → `forktex {facet} login` to capture credentials")


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
