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

"""One place to consume an agent event stream and dispatch by event type.

Replaces the DELTA/USAGE/ERROR/DONE ``async for`` that was hand-rolled in every
CLI (run · scrape · chat REPL). Callers supply small callbacks; this owns the
dispatch and returns the accumulated assistant text.
"""

from __future__ import annotations

from typing import AsyncIterator, Callable, Optional

from forktex.agent.engine.events import AgentEvent, AgentEventType


async def stream_agent_output(
    stream: AsyncIterator[AgentEvent],
    *,
    on_delta: Callable[[str], None],
    on_error: Optional[Callable[[str], None]] = None,
    on_usage: Optional[Callable[[AgentEvent], None]] = None,
    on_done: Optional[Callable[[], None]] = None,
) -> str:
    """Consume ``stream``, dispatching each event, and return the full text.

    ``on_delta`` receives each text chunk (print/emit it). The other callbacks
    are optional. Exceptions raised by the stream propagate to the caller, which
    owns the ``try/except`` (e.g. via ``engine.stream_errors.classify``).
    """
    text = ""
    async for event in stream:
        kind = event.event
        if kind == AgentEventType.DELTA:
            text += event.delta_text
            on_delta(event.delta_text)
        elif kind == AgentEventType.USAGE:
            if on_usage is not None:
                on_usage(event)
        elif kind == AgentEventType.ERROR:
            if on_error is not None:
                on_error(event.error_message)
        elif kind == AgentEventType.DONE:
            if on_done is not None:
                on_done()
    return text


__all__ = ["stream_agent_output"]
