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


from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from forktex.error import AppError, AppErrorCode, to_envelope
from forktex.log import get_logger, get_trace_id

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
    AppErrorCode.CANCELLED: 409,
    AppErrorCode.FAILED: 500,
    AppErrorCode.INTERNAL: 500,
}


class ExceptionEnvelopeMiddleware:
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
            await _send_json(send, _http_status_for(exc), envelope.model_dump())
        except Exception:
            if started or not self._handle_unexpected:
                raise
            logger.exception("unhandled error")
            envelope = to_envelope(AppError("Internal Server Error"), trace_id=get_trace_id())
            await _send_json(send, 500, envelope.model_dump())


class SecurityHeadersMiddleware:
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
                present = {name.lower() for name, _ in headers}
                headers.extend((k, v) for k, v in self._defaults if k not in present)
            await send(message)

        await self._app(scope, receive, send_with_headers)


async def _send_json(send: _Send, status: int, payload: dict[str, Any]) -> None:
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


def _http_status_for(error: AppError) -> int:
    try:
        return _HTTP_STATUS_BY_CODE[AppErrorCode(error.code)]
    except ValueError:
        return 500


__all__ = ["ExceptionEnvelopeMiddleware", "SecurityHeadersMiddleware"]
