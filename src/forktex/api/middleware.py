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


"""Cross-cutting ASGI middleware bundled with the ``[api]`` extra.

Both classes are **pure ASGI** — they take an ASGI app and speak the
``(scope, receive, send)`` protocol directly, so importing this module pulls no
third-party dependency. That is a deliberate departure from the version this
code came from, which subclassed Starlette's ``BaseHTTPMiddleware`` and so
needed ``starlette`` at *import* time; `docs/development.md`'s module checklist
requires the optional dep be imported lazily inside functions, and
:class:`forktex.log.TraceIDMiddleware` already sets the pure-ASGI precedent.
Avoiding ``BaseHTTPMiddleware`` also sidesteps its known interactions with
streaming responses and background tasks.

Request-id / trace-id propagation is NOT here — it is owned by
:class:`forktex.log.TraceIDMiddleware` (single source: it sets the log trace-id
contextvar so logs correlate with the ``X-Request-ID`` header and the
error-envelope ``traceId``). :func:`forktex.api.create_app` wires that one for
you, *outside* the envelope middleware — see the ordering note there.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from forktex.error import AppError, AppErrorCode, to_envelope
from forktex.log import get_logger, get_trace_id

# Minimal ASGI protocol aliases, mirroring `forktex.log` — so this module needs
# no starlette/asgiref dependency to be imported.
_Scope = dict[str, Any]
_Message = dict[str, Any]
_Receive = Callable[[], Awaitable[_Message]]
_Send = Callable[[_Message], Awaitable[None]]
_ASGIApp = Callable[[_Scope, _Receive, _Send], Awaitable[None]]

logger = get_logger(__name__)

_HTTP_STATUS_BY_CODE: dict[AppErrorCode, int] = {
    AppErrorCode.NOT_FOUND: 404,
    AppErrorCode.ALREADY_EXISTS: 409,
    AppErrorCode.BAD_REQUEST: 400,
    AppErrorCode.VALIDATION: 422,
    AppErrorCode.UNAUTHORIZED: 401,
    AppErrorCode.FORBIDDEN: 403,
    AppErrorCode.CONFLICT: 409,
    AppErrorCode.RATE_LIMITED: 429,
    AppErrorCode.UNAVAILABLE: 503,
    AppErrorCode.TIMEOUT: 504,
    # A cancelled job/run isn't a server fault and isn't retryable as-is —
    # 409 matches "the resource's current state conflicts with your request".
    AppErrorCode.CANCELLED: 409,
    # The operation genuinely failed (e.g. a workflow exhausted its retries).
    # Distinct code from INTERNAL so a client can tell "your work failed"
    # apart from "our server broke", even though both render as 500.
    AppErrorCode.FAILED: 500,
    AppErrorCode.INTERNAL: 500,
}


def _http_status_for(error: AppError) -> int:
    """Map an ``AppError``'s ``code`` to an HTTP status.

    ``AppError.code`` has no notion of HTTP — this mapping is owned here, the one
    place that actually needs it. Falls back to 500 for a service's own custom
    code (``code`` is an open ``str``) that isn't in the generic vocabulary.
    """
    try:
        return _HTTP_STATUS_BY_CODE[AppErrorCode(error.code)]
    except ValueError:
        return 500


async def _send_json(send: _Send, status: int, payload: dict[str, Any]) -> None:
    """Emit a complete JSON response over raw ASGI."""
    body = json.dumps(payload).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class ExceptionEnvelopeMiddleware:
    """Convert raised errors into the ``ErrorEnvelope`` wire shape.

    Runs *inside* :class:`forktex.log.TraceIDMiddleware` so the log trace-id
    contextvar is still active when the envelope is built — the response body's
    ``traceId`` matches the ``X-Request-ID`` header and the server logs. This
    ordering is load-bearing, not cosmetic: ``TraceIDMiddleware`` binds the id
    with a context manager that *resets* it on exit, so an envelope built
    anywhere outside it (a Starlette ``Exception`` handler, which runs in the
    outermost ``ServerErrorMiddleware``) would carry a null ``traceId``.

    ``AppError``'s ``code`` maps to an HTTP status via :func:`_http_status_for`
    (``AppError`` itself carries no HTTP status — that is a transport concern
    owned here); when ``handle_unexpected`` is set, any other exception is
    logged and returned as a generic 500 envelope, never leaking internals.
    FastAPI's own ``HTTPException`` / request-validation handling runs closer to
    the route and is left untouched.

    An exception raised *after* the response has started streaming cannot be
    turned into an envelope — the status line is already on the wire — so it is
    re-raised for the server to log and drop the connection.
    """

    def __init__(self, app: _ASGIApp, *, handle_unexpected: bool = True) -> None:
        self._app = app
        self._handle_unexpected = handle_unexpected

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        started = False

        async def send_tracking_start(message: _Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self._app(scope, receive, send_tracking_start)
        except AppError as exc:
            if started:
                raise
            envelope = to_envelope(exc, trace_id=get_trace_id())
            # BaseAppModel sets `serialize_by_alias`, so this is already camelCase.
            await _send_json(send, _http_status_for(exc), envelope.model_dump())
        except Exception:
            if started or not self._handle_unexpected:
                raise
            logger.exception("unhandled error")
            envelope = to_envelope(AppError("Internal Server Error"), trace_id=get_trace_id())
            await _send_json(send, 500, envelope.model_dump())


class SecurityHeadersMiddleware:
    """Add a defensive baseline of HTTP security headers.

    Targets app responses that don't otherwise opt in to security headers — the
    values are conservative defaults that won't break typical JSON APIs. A
    header the application already set is left alone. Consumers needing CSP,
    HSTS, or per-route overrides should install their own middleware.
    """

    DEFAULT_HEADERS: ClassVar[dict[str, str]] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }

    def __init__(self, app: _ASGIApp) -> None:
        self._app = app
        self._defaults = [(k.lower().encode(), v.encode()) for k, v in self.DEFAULT_HEADERS.items()]

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: _Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                # setdefault semantics per header: never clobber one the app set.
                present = {name.lower() for name, _ in headers}
                headers.extend((k, v) for k, v in self._defaults if k not in present)
            await send(message)

        await self._app(scope, receive, send_with_headers)


__all__ = ["ExceptionEnvelopeMiddleware", "SecurityHeadersMiddleware"]
