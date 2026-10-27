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

from collections.abc import AsyncIterator
import contextlib
import asyncio
import uuid

import pytest
import pytest_asyncio

pytest.importorskip("arq", reason="arq not installed")

from datetime import datetime, timedelta, timezone

import forktex.queue as q
from forktex.queue.queue import _failed_count
from forktex.queue import (
    JobCtx,
    JobInfo,
    JobStatus,
    QueueError,
    QueueHealth,
    cancel_job,
    enqueue,
    enqueue_at,
    inspect_job,
    list_jobs,
    make_worker,
    task,
    worker_health,
)


_results: list[str] = []


@task
async def simple_task(ctx: JobCtx, value: str) -> str:
    _results.append(value)
    return f"done:{value}"


@task(retries=1, timeout=30)
async def retryable_task(ctx: JobCtx) -> str:
    return "ok"


_traces: list[tuple[str | None, str | None]] = []


@task
async def trace_probe_task(ctx: JobCtx, value: str) -> str:
    from forktex.log import get_root_trace_id, get_trace_id

    _traces.append((get_trace_id(), get_root_trace_id()))
    _results.append(value)
    return "traced"


@pytest_asyncio.fixture(autouse=True)
async def queue_init(redis_url: str) -> AsyncIterator[None]:
    await q.init(redis_url)
    _results.clear()
    _traces.clear()
    yield
    await q.close()


@pytest.mark.asyncio
async def test_task_registered() -> None:
    assert "simple_task" in q._registry
    assert "retryable_task" in q._registry


@pytest.mark.asyncio
async def test_task_attributes() -> None:
    assert simple_task._queue_name == "default"
    assert retryable_task._job_retries == 1
    assert retryable_task._job_timeout == 30


@pytest.mark.asyncio
async def test_enqueue_returns_job_id(redis_url: str) -> None:
    job_id = await enqueue(simple_task, "hello")
    assert isinstance(job_id, str)
    assert len(job_id) > 0


@pytest.mark.asyncio
async def test_inspect_job_returns_a_typed_snapshot(redis_url: str) -> None:
    job_id = await enqueue(simple_task, "inspect-me")
    info = await inspect_job(job_id)
    assert isinstance(info, JobInfo)
    assert info.job_id == job_id
    assert info.function == "simple_task"
    assert info.status in set(JobStatus)


@pytest.mark.asyncio
async def test_worker_health_is_typed(redis_url: str) -> None:
    health = await worker_health(redis_url)
    assert isinstance(health, QueueHealth)
    assert health.pending >= 0 and health.in_flight >= 0 and health.failed >= 0


@pytest.mark.asyncio
async def test_make_worker_has_registered_functions(redis_url: str) -> None:
    worker = make_worker(redis_url)
    assert hasattr(worker, "functions")

    def _fname(f: object) -> str:
        if callable(f) and hasattr(f, "__name__"):
            return f.__name__
        if hasattr(f, "name"):
            return f.name
        if hasattr(f, "coroutine") and hasattr(f.coroutine, "__name__"):
            return f.coroutine.__name__
        return str(f)

    names = [_fname(f) for f in worker.functions]
    assert "simple_task" in names
    assert "retryable_task" in names


@pytest.mark.asyncio
async def test_worker_executes_task(redis_url: str) -> None:
    await enqueue(simple_task, "worker-test")
    worker = make_worker(redis_url, max_jobs=1)
    worker.poll_delay_s = 0.05

    try:
        await asyncio.wait_for(worker.async_run(), timeout=10)
    except asyncio.TimeoutError, SystemExit:
        pass
    finally:
        try:
            await worker.close()
        except Exception:
            pass

    assert "worker-test" in _results


@pytest.mark.asyncio
async def test_enqueue_at_returns_job_id(redis_url: str) -> None:
    eta = datetime.now(timezone.utc) + timedelta(hours=1)
    job_id = await enqueue_at(simple_task, "scheduled", eta=eta)
    assert isinstance(job_id, str)
    assert len(job_id) > 0
    info = await inspect_job(job_id)
    assert info is None or info.status is not JobStatus.COMPLETE


@pytest.mark.asyncio
async def test_cancel_job_without_a_running_worker_returns_false(redis_url: str) -> None:
    eta = datetime.now(timezone.utc) + timedelta(hours=1)
    job_id = await enqueue_at(simple_task, "never-runs", eta=eta)
    assert await cancel_job(job_id) is False


@pytest.mark.asyncio
async def test_cancel_job_unknown_id_returns_false(redis_url: str) -> None:
    assert await cancel_job("not-a-real-job-id") is False


@task
async def slow_task(ctx: JobCtx) -> str:
    await asyncio.sleep(2)
    return "finished"


@pytest.mark.asyncio
async def test_cancel_job_while_worker_is_running_it_returns_true(redis_url: str) -> None:
    job_id = await enqueue(slow_task)
    worker = make_worker(redis_url, max_jobs=1)
    worker.poll_delay_s = 0.05

    worker_task = asyncio.ensure_future(worker.async_run())
    try:
        await asyncio.sleep(0.3)
        cancelled = await cancel_job(job_id)
        assert cancelled is True
    finally:
        worker_task.cancel()
        try:
            await asyncio.wait_for(worker_task, timeout=5)
        except asyncio.CancelledError, asyncio.TimeoutError, SystemExit:
            pass
        try:
            await worker.close()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_list_jobs_returns_enqueued_job(redis_url: str) -> None:
    job_id = await enqueue(simple_task, "list-me")
    jobs = await list_jobs("default")
    assert isinstance(jobs, list)
    assert any(j.job_id == job_id for j in jobs)


@task(queue="priority-lane")
async def lane_task(ctx: JobCtx, value: str) -> str:
    return value


@pytest.mark.asyncio
async def test_list_jobs_resolves_status_on_the_queue_it_is_listing(redis_url: str) -> None:
    job_id = await enqueue(lane_task, "lane-me")

    listed = await list_jobs("priority-lane")
    mine = [j for j in listed if j.job_id == job_id]
    assert mine, "the job must be listed"
    assert mine[0].status in {JobStatus.QUEUED, JobStatus.DEFERRED}, (
        f"status must resolve on the listed queue, got {mine[0].status!r}"
    )
    assert await list_jobs("priority-lane", status=mine[0].status), "a status filter must match"


@pytest.mark.asyncio
async def test_queue_error_when_not_initialized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(q, "_default", None)
    with pytest.raises(QueueError):
        await enqueue(simple_task, "x")


@pytest.mark.asyncio
async def test_pool_is_cached_not_recreated_per_call(redis_url: str) -> None:
    handle = q.require_default()
    assert await handle.pool() is await handle.pool()


@pytest.mark.asyncio
async def test_init_closes_previous_pool_before_replacing_it(redis_url: str) -> None:
    first = q.require_default()
    await first.pool()
    assert first._pool is not None

    await q.init(redis_url)
    assert first._pool is None, "the replaced handle's pool must be closed and cleared"
    assert q.require_default() is not first, "init() must install a new handle"

    assert await q.require_default().pool() is not None


@pytest.mark.asyncio
async def test_close_clears_the_default_handle(redis_url: str) -> None:
    handle = q.require_default()
    await handle.pool()
    await q.close()
    assert handle._pool is None
    assert q.default() is None


@pytest.mark.asyncio
async def test_two_handles_hold_independent_pools(redis_url: str) -> None:
    one, two = q.Queue(redis_url), q.Queue(redis_url)
    try:
        assert await one.pool() is not await two.pool()
    finally:
        await one.close()
        await two.close()


@pytest.mark.asyncio
async def test_close_without_init_is_idempotent() -> None:
    await q.close()
    await q.close()


def test_queue_error_is_a_runtime_error() -> None:
    assert issubclass(QueueError, RuntimeError)


@pytest.mark.asyncio
async def test_worker_health_counts_pending_on_a_custom_queue(redis_url: str) -> None:
    custom = f"health-q-{uuid.uuid7().hex}"
    await enqueue(simple_task, "hq-1", _queue_name=custom)
    await enqueue(simple_task, "hq-2", _queue_name=custom)

    health = await worker_health(redis_url, queue_name=custom)
    assert health.pending == 2, health

    default_health = await worker_health(redis_url)
    assert default_health.pending >= 0


def test_task_timeout_and_retries_reach_the_arq_worker(redis_url: str) -> None:
    worker = make_worker(redis_url)
    by_name = {f.name: f for f in worker.functions.values()}

    assert by_name["simple_task"].timeout_s == 300
    assert by_name["simple_task"].max_tries == 1

    assert by_name["retryable_task"].timeout_s == 30
    assert by_name["retryable_task"].max_tries == 2


async def _drain_one(redis_url: str) -> None:
    worker = make_worker(redis_url, max_jobs=1)
    worker.poll_delay_s = 0.05
    try:
        await asyncio.wait_for(worker.async_run(), timeout=10)
    except asyncio.TimeoutError, SystemExit:
        pass
    finally:
        with contextlib.suppress(Exception):
            await worker.close()


@pytest.mark.asyncio
async def test_enqueue_carries_the_root_trace_id_into_the_job(redis_url: str) -> None:
    from forktex.log import trace_context

    with trace_context("req-trace-42"):
        await enqueue(trace_probe_task, "payload")

    await _drain_one(redis_url)

    assert "payload" in _results
    assert len(_traces) == 1
    job_trace, job_root = _traces[0]
    assert job_root == "req-trace-42", "the enqueuing request's root trace did not survive Redis"
    assert job_trace == "req-trace-42"


@pytest.mark.asyncio
async def test_a_job_enqueued_with_no_trace_context_still_gets_one(redis_url: str) -> None:
    await enqueue(trace_probe_task, "no-trace")
    await _drain_one(redis_url)

    job_trace, job_root = _traces[0]
    assert job_trace is not None
    assert job_root is not None


@pytest.mark.asyncio
async def test_the_reserved_trace_kwarg_never_reaches_the_task_signature(redis_url: str) -> None:
    from forktex.log import trace_context

    with trace_context("req-strip"):
        await enqueue(trace_probe_task, "stripped")
    await _drain_one(redis_url)

    assert "stripped" in _results, "job did not complete — the reserved kwarg leaked through"


@pytest.mark.asyncio
async def test_an_explicit_trace_kwarg_is_not_overwritten(redis_url: str) -> None:
    from forktex.log import trace_context

    with trace_context("ambient"):
        await enqueue(trace_probe_task, "explicit", **{q.TRACE_KWARG: "caller-wins"})
    await _drain_one(redis_url)

    assert _traces[0][1] == "caller-wins"


def test_drain_timeout_selects_arqs_waiting_shutdown_handler(redis_url: str) -> None:
    assert make_worker(redis_url)._job_completion_wait == 0
    assert make_worker(redis_url, drain_timeout=25)._job_completion_wait == 25


@pytest.mark.asyncio
async def test_a_malformed_inbound_trace_id_is_discarded_not_adopted(redis_url: str) -> None:
    forged = "x\n2026-01-01 00:00:00 | CRITICAL | audit | payment approved"
    await enqueue(trace_probe_task, "screened", **{q.TRACE_KWARG: forged})
    await _drain_one(redis_url)

    job_trace, job_root = _traces[0]
    assert job_trace != forged
    assert "\n" not in (job_trace or "")
    assert job_trace is not None
    assert job_root is not None


@pytest.mark.asyncio
async def test_an_over_long_inbound_trace_id_is_rejected(redis_url: str) -> None:
    await enqueue(trace_probe_task, "toolong", **{q.TRACE_KWARG: "a" * 129})
    await _drain_one(redis_url)

    assert _traces[0][0] != "a" * 129


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 0),
        (b"", 0),
        ("1700000000.0 j_complete=5 j_failed=3 j_retried=0 j_ongoing=0 queued=2", 3),
        (b"1700000000.0 j_complete=5 j_failed=3 queued=2", 3),
        ("1700000000.0 j_complete=5 queued=2", 0),
        ("1700000000.0 j_failed=notanint queued=2", 0),
    ],
)
def test_failed_count_reads_arqs_health_string(raw: str | bytes | None, expected: int) -> None:
    assert _failed_count(raw) == expected
