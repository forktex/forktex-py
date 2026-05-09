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

"""Classify chat-stream exceptions into transient/fatal/unknown.

Used by ``chat_app.py``'s chat-turn exception handler to render
friendlier diagnostics (and avoid making a network blip look the same
as an authentication failure).

The classifier is data-only and importable without prompt_toolkit so it
unit-tests cleanly.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import httpx


Verdict = Literal["transient", "fatal", "unknown"]


@dataclass(frozen=True)
class StreamErrorVerdict:
    """How the chat REPL should react to a stream exception."""

    verdict: Verdict
    message: str
    hint: str = ""

    @property
    def markup(self) -> str:
        """Rich markup ready for ``emit_markup``."""
        if self.verdict == "transient":
            head = "[yellow]stream interrupted[/yellow]"
        elif self.verdict == "fatal":
            head = "[red]fatal[/red]"
        else:
            head = "[red]stream error[/red]"
        body = f"\n{head} — {self.message}"
        if self.hint:
            body += f"\n[dim]{self.hint}[/dim]"
        return body + "\n"


_TRANSIENT_TYPES: tuple[type[BaseException], ...] = (
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    asyncio.TimeoutError,
    ConnectionError,
)


def classify(exc: BaseException) -> StreamErrorVerdict:
    """Map *exc* to a :class:`StreamErrorVerdict`.

    - Network blips → ``transient`` with a "try again" hint.
    - ``IntelligenceAPIError`` with 401/403 → ``fatal`` + suggest
      ``/connect intelligence``.
    - ``IntelligenceAPIError`` with other 4xx/5xx → ``fatal`` with the
      server-supplied message.
    - Anything else → ``unknown`` with the str(exc).
    """
    if isinstance(exc, _TRANSIENT_TYPES):
        return StreamErrorVerdict(
            verdict="transient",
            message=str(exc) or exc.__class__.__name__,
            hint="try the same prompt again — the network looked unstable.",
        )

    api_err = _as_api_error(exc)
    if api_err is not None:
        status = api_err["status"]
        message = api_err["message"]
        if status in (401, 403):
            return StreamErrorVerdict(
                verdict="fatal",
                message=f"auth failed ({status}): {message}",
                hint="run `/connect intelligence` to re-capture credentials.",
            )
        if status in (408, 429):
            return StreamErrorVerdict(
                verdict="transient",
                message=f"server-side throttle ({status}): {message}",
                hint="wait a moment and retry.",
            )
        return StreamErrorVerdict(
            verdict="fatal",
            message=f"API {status}: {message}",
        )

    return StreamErrorVerdict(
        verdict="unknown",
        message=str(exc) or exc.__class__.__name__,
        hint="set FORKTEX_DEBUG=1 to see the traceback on next run.",
    )


def _as_api_error(exc: BaseException) -> dict | None:
    """Try to extract ``(status, message)`` from an Intelligence SDK error.

    Imports ``IntelligenceAPIError`` lazily so this module loads in
    contexts that don't have the SDK fully wired.
    """
    try:
        from forktex_intelligence.client.client import IntelligenceAPIError
    except Exception:  # pragma: no cover — SDK not available
        return None

    if not isinstance(exc, IntelligenceAPIError):
        return None
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return {
        "status": int(status) if status else 0,
        "message": str(exc),
    }


__all__ = ["StreamErrorVerdict", "Verdict", "classify"]
