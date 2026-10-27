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

import functools
import uuid
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

_trace_id: ContextVar[str | None] = ContextVar("forktex_log.trace_id", default=None)

_extra_fields: ContextVar[dict[str, object] | None] = ContextVar("forktex_log.extra", default=None)

_run_id: str | None = None

_root_trace_id: ContextVar[str | None] = ContextVar("forktex_log.root_trace_id", default=None)


def get_run_id() -> str:
    global _run_id
    if _run_id is None:
        _run_id = str(uuid.uuid7())
    return _run_id


def reset_run_id() -> str:
    global _run_id
    _run_id = str(uuid.uuid7())
    return _run_id


def get_trace_id() -> str | None:
    return _trace_id.get()


def get_root_trace_id() -> str | None:
    return _root_trace_id.get()


def set_trace_id(value: str | None) -> None:
    _trace_id.set(value)


@contextmanager
def trace_context(value: str | None = None) -> Generator[str]:
    trace_id = value or str(uuid.uuid7())
    token = _trace_id.set(trace_id)
    root_token = _root_trace_id.set(trace_id) if _root_trace_id.get() is None else None
    try:
        yield trace_id
    finally:
        _trace_id.reset(token)
        if root_token is not None:
            _root_trace_id.reset(root_token)


@asynccontextmanager
async def async_trace_context(value: str | None = None) -> AsyncGenerator[str]:
    trace_id = value or str(uuid.uuid7())
    token = _trace_id.set(trace_id)
    root_token = _root_trace_id.set(trace_id) if _root_trace_id.get() is None else None
    try:
        yield trace_id
    finally:
        _trace_id.reset(token)
        if root_token is not None:
            _root_trace_id.reset(root_token)


def bind_current_context[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    trace = _trace_id.get()
    root = _root_trace_id.get()
    fields = _extra_fields.get(None)

    @functools.wraps(fn)
    def _run(*args: P.args, **kwargs: P.kwargs) -> R:
        trace_token = _trace_id.set(trace)
        root_token = _root_trace_id.set(root)
        fields_token = _extra_fields.set(fields)
        try:
            return fn(*args, **kwargs)
        finally:
            _trace_id.reset(trace_token)
            _root_trace_id.reset(root_token)
            _extra_fields.reset(fields_token)

    return _run


def get_extra_fields() -> dict[str, object]:
    return _extra_fields.get(None) or {}


@contextmanager
def log_context(**fields: object) -> Generator[None]:
    merged = {**get_extra_fields(), **fields}
    token = _extra_fields.set(merged)
    try:
        yield
    finally:
        _extra_fields.reset(token)


@asynccontextmanager
async def async_log_context(**fields: object) -> AsyncGenerator[None]:
    merged = {**get_extra_fields(), **fields}
    token = _extra_fields.set(merged)
    try:
        yield
    finally:
        _extra_fields.reset(token)


__all__ = [
    "async_log_context",
    "async_trace_context",
    "get_extra_fields",
    "get_root_trace_id",
    "get_trace_id",
    "log_context",
    "set_trace_id",
    "trace_context",
]
