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

"""Chat REPL on top of ``prompt_toolkit``.

Layout:
    [scrollable conversation]
    [optional facet cards — ConditionalContainer]
    [input line with slash autocompletion]
    [hint bar listing slash commands]

Streaming: the intelligence agent yields SSE delta events; each delta is
appended to the conversation ``Buffer`` and the app is invalidated so the
next redraw paints the new tokens. The input line stays pinned at the bottom.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.lexers import SimpleLexer
from prompt_toolkit.styles import Style
from rich.console import Console

from forktex.agent.auth.status import collect_auth_status
from forktex.agent.auth.types import FACETS, AuthState
from forktex.agent.root_loop.slash import (
    SERVICES,
    SLASH_COMMANDS,
    SlashContext,
    dispatch,
)


# ── state ────────────────────────────────────────────────────────────────────


@dataclass
class ChatAppState:
    show_cards: bool = False
    flash_cards_until: float = (
        0.0  # monotonic seconds; show_cards forced True until then
    )
    cards: dict[str, AuthState] = field(default_factory=dict)
    transcript: list[str] = field(default_factory=list)  # plain strings, for /history
    buffer: Optional[Buffer] = None
    exit_reason: str = ""  # "" | "menu" | "quit"


# ── rich → ansi capture ──────────────────────────────────────────────────────


def _render_markup(markup: str) -> str:
    """Render rich markup to an ANSI string usable in the pt buffer."""
    sio = io.StringIO()
    Console(file=sio, force_terminal=True, color_system="truecolor", width=120).print(
        markup
    )
    return sio.getvalue()


# ── autocomplete ─────────────────────────────────────────────────────────────


class SlashCompleter(Completer):
    """Live-completes slash commands and their service arguments.

    Service suggestions carry a one-line description via ``display_meta`` so
    the dropdown doubles as a cheat-sheet.
    """

    def get_completions(self, document: Document, complete_event):  # noqa: ANN001
        text = document.text_before_cursor
        # Arg-position completion (e.g. `/connect cl`).
        if " " in text and text.startswith("/"):
            head, _, tail = text.partition(" ")
            cmd = SLASH_COMMANDS.get(head.lower())
            if cmd and cmd.arg_completer:
                service_meta = dict(SERVICES)
                for opt in cmd.arg_completer():
                    if opt.startswith(tail.strip()):
                        yield Completion(
                            opt,
                            start_position=-len(tail.strip()),
                            display_meta=service_meta.get(opt, ""),
                        )
            return
        # Command-name completion.
        if text.startswith("/"):
            for name in SLASH_COMMANDS:
                if name.startswith(text):
                    yield Completion(
                        name,
                        start_position=-len(text),
                        display_meta=SLASH_COMMANDS[name].description,
                    )


# ── rendering ────────────────────────────────────────────────────────────────


def _cards_line(state: ChatAppState) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    for facet in FACETS:
        s = state.cards.get(facet)
        if not s or not s.configured:
            parts.append(("class:facet-off", f" ✗ {facet} "))
        elif s.reachable is True:
            parts.append(("class:facet-on", f" ✓ {facet} "))
        elif s.reachable is False:
            parts.append(("class:facet-warn", f" ⚠ {facet} "))
        else:
            parts.append(("class:facet-on", f" ✓ {facet} "))
        parts.append(("", " "))
    return parts or [("", "")]


def _hint_line() -> list[tuple[str, str]]:
    names = " · ".join(name for name in SLASH_COMMANDS)
    return [("class:hint", f" {names} ")]


_STYLE = Style.from_dict(
    {
        "conversation": "",
        "facet-on": "bg:ansigreen fg:ansiblack bold",
        "facet-off": "bg:ansiblack fg:ansibrightblack",
        "facet-warn": "bg:ansiyellow fg:ansiblack",
        "hint": "fg:ansibrightblack",
        "prompt": "fg:ansicyan bold",
        "status": "fg:ansigreen italic",
        "sysline": "fg:ansibrightblack italic",
    }
)


# ── app factory ──────────────────────────────────────────────────────────────


def build_app(
    state: ChatAppState,
    agent_loop: Any,
    tool_server: Any,
    project_root: str,
) -> Application[str]:
    """Construct the prompt_toolkit Application for the chat REPL."""

    conversation_buffer = Buffer(read_only=Condition(lambda: True))
    state.buffer = conversation_buffer
    input_buffer = Buffer(
        multiline=False,
        completer=SlashCompleter(),
        complete_while_typing=True,
    )

    def emit(text: str) -> None:
        """Append raw text to the scroll buffer (used for streamed deltas)."""
        conversation_buffer.set_document(
            Document(
                conversation_buffer.text + text,
                cursor_position=len(conversation_buffer.text) + len(text),
            ),
            bypass_readonly=True,
        )
        state.transcript.append(text)

    def emit_markup(markup: str) -> None:
        emit(_render_markup(markup))

    def exit_signal(reason: str) -> None:
        state.exit_reason = reason
        app.exit(result=reason)

    ctx = SlashContext(
        app_state=state,
        agent_loop=agent_loop,
        tool_server=tool_server,
        project_root=project_root,
        emit=emit,
        emit_markup=emit_markup,
        exit_signal=exit_signal,
    )

    async def handle_submit(buf: Buffer) -> bool:
        line = buf.text.strip()
        if not line:
            return False
        buf.text = ""

        # Echo user input into transcript.
        emit_markup(f"[bold cyan]>[/bold cyan] {line}")
        emit("\n")

        if line.startswith("/"):
            result = await dispatch(ctx, line)
            if result:
                emit_markup(f"[dim]{result}[/dim]")
                emit("\n")
            return False

        # Regular chat turn — stream through the agent loop.
        from forktex_intelligence.streams import SSEEventType

        emit_markup("[bold green]assistant:[/bold green] ")
        try:
            async for event in agent_loop.chat_stream(line):
                if event.event == SSEEventType.DELTA:
                    emit(event.delta_text)
                elif event.event == SSEEventType.ERROR:
                    emit_markup(f"\n[red]error:[/red] {event.error_message}\n")
                elif event.event == SSEEventType.DONE:
                    pass
        except Exception as exc:
            emit_markup(f"\n[red]stream error:[/red] {exc}\n")
        emit("\n")
        return False

    input_buffer.accept_handler = lambda buf: bool(
        __import__("asyncio").create_task(handle_submit(buf))
    )

    # ── key bindings (quick-casts) ────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("c-k")
    def _toggle_cards(event):  # noqa: ANN001
        state.show_cards = not state.show_cards

    @kb.add("c-l")
    def _clear(event):  # noqa: ANN001
        conversation_buffer.set_document(Document("", 0), bypass_readonly=True)

    @kb.add("c-h")
    def _history(event):  # noqa: ANN001
        emit_markup("[dim]— full transcript —[/dim]")
        emit("\n")
        for chunk in state.transcript:
            emit(chunk)

    @kb.add("c-d")
    @kb.add("c-c")
    def _exit(event):  # noqa: ANN001
        exit_signal("menu")

    # ── layout ────────────────────────────────────────────────────────────────
    conversation_window = Window(
        content=BufferControl(buffer=conversation_buffer, lexer=SimpleLexer()),
        wrap_lines=True,
    )

    cards_window = Window(
        content=FormattedTextControl(text=lambda: _cards_line(state)),
        height=1,
        style="class:cards",
    )

    input_window = Window(
        content=BufferControl(
            buffer=input_buffer,
            input_processors=[BeforeInput("> ", style="class:prompt")],
        ),
        height=1,
        dont_extend_height=True,
    )

    hint_window = Window(
        content=FormattedTextControl(text=_hint_line),
        height=1,
        style="class:hint",
    )

    def _cards_visible() -> bool:
        if state.flash_cards_until and time.monotonic() < state.flash_cards_until:
            return True
        return state.show_cards

    root = HSplit(
        [
            conversation_window,
            ConditionalContainer(cards_window, filter=Condition(_cards_visible)),
            input_window,
            hint_window,
        ]
    )

    app: Application[str] = Application(
        layout=Layout(root, focused_element=input_window),
        key_bindings=kb,
        full_screen=True,
        mouse_support=True,
        style=_STYLE,
    )
    return app


# ── entry ────────────────────────────────────────────────────────────────────


async def run_chat(
    agent_loop: Any,
    tool_server: Any,
    project_root: str,
    *,
    seed_welcome: Optional[str] = None,
) -> str:
    """Run the chat application until the user exits. Returns the exit reason."""
    state = ChatAppState()
    # Preload auth state for the (hidden) cards; the flash after a /login will
    # re-populate this with fresh probes.
    try:
        state.cards = await collect_auth_status(project_root, probe=False)
    except Exception:
        state.cards = {}

    app = build_app(state, agent_loop, tool_server, project_root)

    if seed_welcome:
        app_buffer: Buffer = app.layout.container.children[0].content.buffer  # type: ignore[attr-defined]
        app_buffer.set_document(
            Document(seed_welcome + "\n", len(seed_welcome) + 1), bypass_readonly=True
        )

    try:
        return await app.run_async() or "quit"
    except (KeyboardInterrupt, EOFError):  # fmt: skip
        return "quit"
