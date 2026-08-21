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

"""Tests for forktex.log's trace_context()/async_trace_context() and the
trace_id/root_trace_id contextvars they scope — usable in any Python process,
not just behind TraceIDMiddleware."""

from __future__ import annotations

import pytest

from forktex.log import async_trace_context, get_root_trace_id, get_trace_id, set_trace_id, trace_context


def test_trace_context_mints_when_no_value_given():
    with trace_context() as trace_id:
        assert get_trace_id() == trace_id
        assert len(trace_id) == 36


def test_trace_context_uses_explicit_value():
    with trace_context("job-abc") as trace_id:
        assert trace_id == "job-abc"
        assert get_trace_id() == "job-abc"


def test_trace_context_restores_previous_value_on_exit():
    set_trace_id("outer")
    with trace_context("inner"):
        assert get_trace_id() == "inner"
    assert get_trace_id() == "outer"


def test_trace_context_restores_on_exception():
    set_trace_id("outer")
    with pytest.raises(ValueError):
        with trace_context("inner"):
            raise ValueError("boom")
    assert get_trace_id() == "outer"


@pytest.mark.asyncio
async def test_async_trace_context_scopes_and_restores():
    set_trace_id("outer")
    async with async_trace_context("job-99") as trace_id:
        assert trace_id == "job-99"
        assert get_trace_id() == "job-99"
    assert get_trace_id() == "outer"


def test_trace_context_establishes_root_trace_id_once():
    assert get_root_trace_id() is None
    with trace_context("outer") as outer_id:
        assert get_root_trace_id() == outer_id
        with trace_context("inner") as inner_id:
            assert inner_id != outer_id
            assert get_root_trace_id() == outer_id  # unchanged by the nested call
        assert get_root_trace_id() == outer_id
    assert get_root_trace_id() is None


@pytest.mark.asyncio
async def test_async_trace_context_shares_root_across_nesting():
    async with async_trace_context("outer") as outer_id:
        async with async_trace_context("inner") as inner_id:
            assert inner_id != outer_id
            assert get_root_trace_id() == outer_id
    assert get_root_trace_id() is None


# ---------------------------------------------------------------------------
# execution-context boundaries
#
# `trace_id` lives in a ContextVar, so where it survives is decided by whether
# the boundary copies the context. These pin the real behaviour — including the
# places it is LOST — so a future change to any of them is a deliberate one and
# `docs/log.md`'s propagation table stays honest.
# ---------------------------------------------------------------------------


def test_a_plain_thread_does_not_inherit_the_trace():
    """`threading.Thread` starts with a fresh empty context, not a copy of its
    parent's. Work handed to a raw thread must re-bind the trace itself."""
    import threading

    seen: list[str | None] = []
    with trace_context("T-1"):
        t = threading.Thread(target=lambda: seen.append(get_trace_id()))
        t.start()
        t.join()

    assert seen == [None]


def test_a_thread_pool_submit_does_not_inherit_the_trace():
    from concurrent.futures import ThreadPoolExecutor

    with trace_context("T-2"), ThreadPoolExecutor(1) as pool:
        assert pool.submit(get_trace_id).result() is None


async def test_asyncio_to_thread_does_inherit_the_trace():
    """`asyncio.to_thread` copies the context; `loop.run_in_executor` does not. This is
    the difference that decides whether a blocking call keeps its trace."""
    import asyncio

    async with async_trace_context("T-3"):
        assert await asyncio.to_thread(get_trace_id) == "T-3"


async def test_run_in_executor_does_not_inherit_the_trace():
    import asyncio

    async with async_trace_context("T-4"):
        loop = asyncio.get_running_loop()
        assert await loop.run_in_executor(None, get_trace_id) is None


async def test_a_child_task_inherits_the_trace_at_creation():
    import asyncio

    async def probe() -> str | None:
        return get_trace_id()

    async with async_trace_context("T-5"):
        assert await asyncio.create_task(probe()) == "T-5"


# ---------------------------------------------------------------------------
# run_id — attributability, distinct from correlation
# ---------------------------------------------------------------------------


def test_run_id_is_always_present_even_with_no_trace_scope():
    """The point of `run_id`: a line logged outside any scope is still attributable
    to a process invocation. `trace_id` is legitimately None there."""
    from forktex.log import get_run_id

    assert get_trace_id() is None
    assert get_run_id()


def test_run_id_is_stable_across_contexts_and_threads():
    """It is a process identity, so unlike a ContextVar it must be identical in every
    thread — a per-thread value would not let you group a process's own lines."""
    import threading

    from forktex.log import get_run_id

    baseline = get_run_id()
    seen: list[str] = []
    threads = [threading.Thread(target=lambda: seen.append(get_run_id())) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert seen == [baseline] * 3
    with trace_context("T-x"):
        assert get_run_id() == baseline


def test_run_id_is_not_used_as_a_trace_id_fallback():
    """Reusing one id for every unscoped line would make `trace_id` match thousands of
    unrelated records — the appearance of correlation, not correlation."""
    from forktex.log import get_run_id

    assert get_trace_id() is None
    assert get_run_id() != get_trace_id()


# ---------------------------------------------------------------------------
# bind_current_context — the thread-boundary escape hatch
# ---------------------------------------------------------------------------


def test_bind_current_context_carries_the_trace_into_a_thread_pool():
    from concurrent.futures import ThreadPoolExecutor

    from forktex.log import bind_current_context

    with trace_context("T-6"), ThreadPoolExecutor(1) as pool:
        assert pool.submit(bind_current_context(get_trace_id)).result() == "T-6"


def test_bind_current_context_carries_structured_fields_too():
    from concurrent.futures import ThreadPoolExecutor

    from forktex.log import bind_current_context, log_context

    def read() -> dict[str, object]:
        from forktex.log import get_extra_fields

        return get_extra_fields()

    with trace_context("T-7"), log_context(org="acme"), ThreadPoolExecutor(1) as pool:
        assert pool.submit(bind_current_context(read)).result() == {"org": "acme"}


def test_bind_current_context_resumes_the_scope_rather_than_nesting_a_new_one():
    """The wrapped call is the same logical scope continued in another thread, so it
    must keep the trace id — not mint a fresh one under the same root, which is what
    `trace_context()` would do."""
    from concurrent.futures import ThreadPoolExecutor

    from forktex.log import bind_current_context

    def both() -> tuple[str | None, str | None]:
        return get_trace_id(), get_root_trace_id()

    with trace_context("T-8"), ThreadPoolExecutor(1) as pool:
        assert pool.submit(bind_current_context(both)).result() == ("T-8", "T-8")


def test_bind_current_context_captures_at_wrap_time_not_call_time():
    """Documented footgun: wrapping inside the worker captures the worker's empty
    context. Pinned so the semantics cannot drift silently."""
    from forktex.log import bind_current_context

    with trace_context("T-9"):
        wrapped = bind_current_context(get_trace_id)
    # The scope has exited, but the wrapper still replays what it captured.
    assert wrapped() == "T-9"


def test_bind_current_context_restores_the_previous_context_after_running():
    from forktex.log import bind_current_context

    with trace_context("outer"):
        wrapped = bind_current_context(get_trace_id)
        with trace_context("inner"):
            assert wrapped() == "outer"
            assert get_trace_id() == "inner", "the wrapper leaked its binding"
