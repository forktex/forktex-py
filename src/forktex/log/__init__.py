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

import logging
import logging.handlers
import os
import re
import sys
from collections.abc import Awaitable, Callable
from queue import SimpleQueue
from typing import Any

from forktex.log._context import (
    async_log_context,
    async_trace_context,
    bind_current_context,
    get_extra_fields,
    get_root_trace_id,
    get_run_id,
    get_trace_id,
    log_context,
    reset_run_id,
    set_trace_id,
    trace_context,
)
from forktex.log._decorators import traced
from forktex.log._formatter import HumanFormatter, JsonFormatter

_Scope = dict[str, Any]
_Message = dict[str, Any]
_Receive = Callable[[], Awaitable[_Message]]
_Send = Callable[[_Message], Awaitable[None]]
_ASGIApp = Callable[[_Scope, _Receive, _Send], Awaitable[None]]

_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_queue_listener: logging.handlers.QueueListener | None = None

logging.getLogger("forktex").addHandler(logging.NullHandler())


class ContextFilter(logging.Filter):
    def __init__(self, service: str | None = None) -> None:
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        record.root_trace_id = get_root_trace_id()
        record.run_id = get_run_id()
        record.service = self._service
        record._forktex_extra = get_extra_fields()
        return True


_ContextFilter = ContextFilter


class _InProcessQueueHandler(logging.handlers.QueueHandler):
    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return record


DEFAULT_QUIET_LOGGERS: list[str] = [
    "uvicorn.access",
    "uvicorn.error",
    "sqlalchemy.engine",
    "httpx",
    "httpcore",
    "asyncio",
]


def _env_bool(name: str) -> bool | None:
    val = os.getenv(name)
    if val is None:
        return None
    return val.strip().lower() in {"1", "true", "yes", "on"}


def setup_logging(
    *,
    service: str | None = None,
    level: int | str | None = None,
    debug: bool | None = None,
    json: bool | None = None,
    quiet: list[str] | None = None,
    quiet_level: int = logging.WARNING,
    quiet_defaults: bool = True,
    fmt: str | None = None,
    datefmt: str | None = None,
    handlers: list[logging.Handler] | None = None,
    queue: bool = False,
) -> None:
    if debug is None:
        debug = _env_bool("FORKTEX_LOG_DEBUG") or False
    if json is None:
        json = _env_bool("FORKTEX_LOG_JSON")
    if level is None:
        level = os.getenv("FORKTEX_LOG_LEVEL", logging.INFO)

    if debug:
        level = logging.DEBUG

    effective_json = (not debug) if json is None else json

    reset_run_id()

    root = logging.getLogger()
    global _queue_listener

    root.setLevel(level)
    root.handlers.clear()
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None

    formatter = JsonFormatter() if effective_json else HumanFormatter(fmt=fmt, datefmt=datefmt)
    target_handlers = handlers if handlers is not None else [logging.StreamHandler(sys.stdout)]
    for h in target_handlers:
        h.setLevel(level)
        h.setFormatter(formatter)

    if queue:
        log_queue: SimpleQueue[logging.LogRecord] = SimpleQueue()
        queue_handler = _InProcessQueueHandler(log_queue)
        queue_handler.setLevel(level)
        queue_handler.addFilter(ContextFilter(service=service))
        root.addHandler(queue_handler)

        _queue_listener = logging.handlers.QueueListener(log_queue, *target_handlers, respect_handler_level=True)
        _queue_listener.start()
    else:
        for h in target_handlers:
            h.addFilter(ContextFilter(service=service))
            root.addHandler(h)

    quiet_names = (DEFAULT_QUIET_LOGGERS if quiet_defaults else []) + (quiet or [])
    for name in quiet_names:
        logging.getLogger(name).setLevel(quiet_level)


def shutdown_logging() -> None:
    global _queue_listener
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class TraceIDMiddleware:
    def __init__(self, app: _ASGIApp, *, header: str = "X-Request-ID") -> None:
        self._app = app
        self._header = header.lower().encode()

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        inbound = dict(scope["headers"]).get(self._header)
        candidate = inbound.decode(errors="replace") if inbound else None
        valid = candidate if candidate and _TRACE_ID_RE.match(candidate) else None

        async def send_with_header(message: _Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((self._header, trace_id.encode()))
            await send(message)

        with trace_context(valid) as trace_id:
            await self._app(scope, receive, send_with_header)


__all__ = [
    "DEFAULT_QUIET_LOGGERS",
    "ContextFilter",
    "TraceIDMiddleware",
    "async_log_context",
    "async_trace_context",
    "bind_current_context",
    "get_extra_fields",
    "get_logger",
    "get_root_trace_id",
    "get_run_id",
    "get_trace_id",
    "log_context",
    "set_trace_id",
    "setup_logging",
    "shutdown_logging",
    "trace_context",
    "traced",
]
