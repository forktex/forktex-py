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

"""Contextvar storage for trace_id and structured log fields.

Uses ``contextvars.ContextVar`` so values are coroutine-scoped — no leakage
between concurrent async tasks even when running in the same thread.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

# Trace/request identifier — set by middleware or manually via set_trace_id()
_trace_id: ContextVar[str | None] = ContextVar("forktex_log.trace_id", default=None)

# Arbitrary structured fields per coroutine context. Values are opaque (``object``):
# the logger only serialises them, it never treats them as a specific type.
# Sentinel None avoids the shared-mutable-default problem: if we used
# default={}, all coroutines that never call log_context() would share the
# same dict object and mutations would leak across task boundaries.
_extra_fields: ContextVar[dict[str, object] | None] = ContextVar("forktex_log.extra", default=None)

# One id per process invocation, minted lazily on first read and never reset.
# Deliberately a plain module global, not a ContextVar: it must be identical in
# every thread, task and context of the process, which is exactly what a
# ContextVar does not give you (a new thread starts with an empty context and
# would mint its own).
_run_id: str | None = None

# Stable across a whole chain of nested trace_context()/async_trace_context()
# calls (an HTTP request, a worker job and everything it calls) — set once by
# whichever scope enters first, unlike trace_id which is fresh per call.
_root_trace_id: ContextVar[str | None] = ContextVar("forktex_log.root_trace_id", default=None)


def get_run_id() -> str:
    """Identify this process invocation. Always a value, never ``None``.

    This is the field that makes every log line attributable. ``trace_id`` answers
    "which unit of work" and is legitimately absent outside a scope; ``run_id``
    answers "which process emitted this" and is always knowable, so it is emitted
    on every record.

    It is deliberately *not* a fallback for ``trace_id``. Reusing one id for every
    unscoped line would make ``trace_id`` match thousands of unrelated records —
    the appearance of correlation rather than correlation.

    Minted on first use (a time-ordered ``uuid7``) so importing the module costs
    nothing, and stable for the life of the process.
    """
    global _run_id
    if _run_id is None:
        _run_id = str(uuid.uuid7())
    return _run_id


def reset_run_id() -> str:
    """Mint a fresh ``run_id``. Called by ``setup_logging`` so each configured run
    is distinguishable; also useful in tests. Returns the new value."""
    global _run_id
    _run_id = str(uuid.uuid7())
    return _run_id


def get_trace_id() -> str | None:
    return _trace_id.get()


def get_root_trace_id() -> str | None:
    return _root_trace_id.get()


def set_trace_id(value: str | None) -> None:
    """Manually set the trace ID for the current context (non-async callers)."""
    _trace_id.set(value)


@contextmanager
def trace_context(value: str | None = None) -> Generator[str]:
    """Sync context manager — scope a trace_id to this block, then restore
    whatever was set before it (never leaves it dangling like a bare
    ``set_trace_id()`` can). Mints a time-ordered ``uuid7`` if ``value`` is
    omitted.

    The same primitive ``TraceIDMiddleware`` uses per-request — usable in any
    Python process (CLI script, worker job loop, background task), not just
    behind an ASGI app::

        with trace_context(f"job-{job_id}"):
            logger.info("processing")   # → {..."trace_id": "job-..."}
        # trace_id is restored to whatever it was before the block

    Whichever call is outermost (an HTTP request, or the outermost nested
    call in a worker/CLI process) also establishes ``root_trace_id`` — every
    nested ``trace_context()``/``async_trace_context()`` call gets its own
    fresh ``trace_id`` but shares that same ``root_trace_id``, so you can
    correlate one step (``trace_id``) or the whole chain (``root_trace_id``).
    """
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
    """Async counterpart of :func:`trace_context` (coroutine-scoped), with the
    same ``root_trace_id`` establishment behavior.

    async with async_trace_context() as trace_id:
        await process_job()
    """
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
    """Wrap ``fn`` so it re-binds the *calling* context's trace when it later runs.

    For the boundaries that do not copy contextvars — ``threading.Thread``,
    ``ThreadPoolExecutor.submit``, ``loop.run_in_executor`` — work handed across
    them logs with no ``trace_id`` at all. Capture at hand-off, restore at run::

        from forktex.log import bind_current_context

        with ThreadPoolExecutor(4) as pool:
            pool.submit(bind_current_context(work), payload)

    The wrapper reads the trace at *wrap* time, which must therefore happen in the
    context you want carried — wrapping inside the worker thread captures nothing.
    Also carries the structured fields from any surrounding ``log_context()``.

    Unnecessary where the boundary already copies the context: ``await``,
    ``asyncio.create_task``, ``asyncio.to_thread``, and anyio's threadpool (so
    FastAPI's sync ``def`` routes). Cannot help across a process boundary — nothing
    in memory survives that; pass the id in the payload instead.
    """
    trace = _trace_id.get()
    root = _root_trace_id.get()
    fields = _extra_fields.get(None)

    @functools.wraps(fn)
    def _run(*args: P.args, **kwargs: P.kwargs) -> R:
        trace_token = _trace_id.set(trace)
        # Set root directly rather than through `trace_context`: this is the *same*
        # logical scope resumed in another thread, not a nested step, so it must not
        # mint a new trace_id or re-root the chain.
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
    """Return the current structured log fields, never None."""
    return _extra_fields.get(None) or {}


@contextmanager
def log_context(**fields: object) -> Generator[None]:
    """Sync context manager — inject structured fields into all log records
    emitted within the block.

        with log_context(org_id=str(org_id), user_id=str(user_id)):
            logger.info("processing")   # → {..."org_id": "...", "user_id": "..."}
    """
    merged = {**get_extra_fields(), **fields}
    token = _extra_fields.set(merged)
    try:
        yield
    finally:
        _extra_fields.reset(token)


@asynccontextmanager
async def async_log_context(**fields: object) -> AsyncGenerator[None]:
    """Async context manager — inject structured fields into all log records
    emitted within the async block (coroutine-scoped).

        async with async_log_context(org_id=str(org_id)):
            await process()
    """
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
