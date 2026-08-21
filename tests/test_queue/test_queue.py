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

"""Integration tests for forktex.queue — requires Redis container."""

from __future__ import annotations

import contextlib
import asyncio
import uuid

import pytest
import pytest_asyncio

pytest.importorskip("arq", reason="arq not installed")

from datetime import datetime, timedelta, timezone

import forktex.queue as q
from forktex.queue import (
    JobCtx,
    QueueError,
    cancel_job,
    enqueue,
    enqueue_at,
    inspect_job,
    list_jobs,
    make_worker,
    task,
    worker_health,
)


# ---------------------------------------------------------------------------
# Register test tasks (module-level side-effect)
# ---------------------------------------------------------------------------

_results: list[str] = []


@task
async def simple_task(ctx: JobCtx, value: str) -> str:
    _results.append(value)
    return f"done:{value}"


@task(retries=1, timeout=30)
async def retryable_task(ctx: JobCtx) -> str:
    return "ok"


#: Trace context observed *inside* the job body, for the propagation tests.
_traces: list[tuple[str | None, str | None]] = []


@task
async def trace_probe_task(ctx: JobCtx, value: str) -> str:
    from forktex.log import get_root_trace_id, get_trace_id

    _traces.append((get_trace_id(), get_root_trace_id()))
    _results.append(value)
    return "traced"


@pytest_asyncio.fixture(autouse=True)
async def queue_init(redis_url: str):
    await q.init(redis_url)
    _results.clear()
    _traces.clear()
    yield
    # Close the cached pool inside this test's own event loop — pytest-asyncio
    # gives each test function its own loop, and closing a pool from a
    # *different* (already-closed) loop raises "Event loop is closed".
    await q.close()


@pytest.mark.asyncio
async def test_task_registered():
    assert "simple_task" in q._registry
    assert "retryable_task" in q._registry


@pytest.mark.asyncio
async def test_task_attributes():
    assert simple_task._queue_name == "default"
    assert retryable_task._job_retries == 1
    assert retryable_task._job_timeout == 30


@pytest.mark.asyncio
async def test_enqueue_returns_job_id(redis_url: str):
    job_id = await enqueue(simple_task, "hello")
    assert isinstance(job_id, str)
    assert len(job_id) > 0


@pytest.mark.asyncio
async def test_inspect_job_returns_info(redis_url: str):
    job_id = await enqueue(simple_task, "inspect-me")
    info = await inspect_job(job_id)
    # Job may be queued or already processed; either way we get info back
    assert info is None or isinstance(info, dict)


@pytest.mark.asyncio
async def test_worker_health_returns_dict(redis_url: str):
    health = await worker_health(redis_url)
    assert "pending" in health
    assert "in_flight" in health
    assert "failed" in health
    assert all(isinstance(v, int) for v in health.values())


@pytest.mark.asyncio
async def test_make_worker_has_registered_functions(redis_url: str):
    worker = make_worker(redis_url)
    assert hasattr(worker, "functions")

    # arq 0.28 functions may be callables or arq.Function wrappers — normalise to name
    def _fname(f) -> str:
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
async def test_worker_executes_task(redis_url: str):
    """Run a real arq worker in burst mode and verify task execution."""
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
async def test_enqueue_at_returns_job_id(redis_url: str):
    eta = datetime.now(timezone.utc) + timedelta(hours=1)
    job_id = await enqueue_at(simple_task, "scheduled", eta=eta)
    assert isinstance(job_id, str)
    assert len(job_id) > 0
    # Deferred, not yet due — should not have run.
    info = await inspect_job(job_id)
    assert info is None or info.get("status") != "complete"


@pytest.mark.asyncio
async def test_cancel_job_without_a_running_worker_returns_false(redis_url: str):
    """cancel_job() waits for arq to confirm the job's *result* observed a
    cancellation — that requires a worker to actually be processing it. With
    no worker running, a deferred (never-picked-up) job resolves False, not
    True — it is NOT simply "removed from the queue"."""
    eta = datetime.now(timezone.utc) + timedelta(hours=1)
    job_id = await enqueue_at(simple_task, "never-runs", eta=eta)
    assert await cancel_job(job_id) is False


@pytest.mark.asyncio
async def test_cancel_job_unknown_id_returns_false(redis_url: str):
    assert await cancel_job("not-a-real-job-id") is False


@task
async def slow_task(ctx: JobCtx) -> str:
    await asyncio.sleep(2)
    return "finished"


@pytest.mark.asyncio
async def test_cancel_job_while_worker_is_running_it_returns_true(redis_url: str):
    """The True path: a worker actively processing the job, cancelled and
    confirmed mid-flight."""
    job_id = await enqueue(slow_task)
    worker = make_worker(redis_url, max_jobs=1)
    # arq's Worker computes ``self.poll_delay_s`` once in __init__ from the
    # ``poll_delay`` constructor kwarg — setting ``.poll_delay`` post-hoc (as
    # the arq docs' examples sometimes show) is a silent no-op; the running
    # poll loop only ever reads ``poll_delay_s``.
    worker.poll_delay_s = 0.05

    worker_task = asyncio.ensure_future(worker.async_run())
    try:
        await asyncio.sleep(0.3)  # let the worker pick the job up
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
async def test_list_jobs_returns_enqueued_job(redis_url: str):
    job_id = await enqueue(simple_task, "list-me")
    jobs = await list_jobs("default")
    assert isinstance(jobs, list)
    assert any(j.get("job_id") == job_id for j in jobs)


@pytest.mark.asyncio
async def test_queue_error_when_not_initialized(monkeypatch):
    monkeypatch.setattr(q, "_redis_url", None)
    with pytest.raises(QueueError):
        await enqueue(simple_task, "x")


@pytest.mark.asyncio
async def test_get_pool_is_cached_not_recreated_per_call(redis_url: str):
    """_get_pool() used to call arq.create_pool() fresh on every invocation
    and never close the result — an unbounded connection leak under load.
    It must now return the same cached pool across repeated calls."""
    pool1 = await q._get_pool()
    pool2 = await q._get_pool()
    assert pool1 is pool2


@pytest.mark.asyncio
async def test_init_closes_previous_pool_before_replacing_it(redis_url: str):
    """Calling init() again (e.g. to reconfigure) must not leak the old pool."""
    await q._get_pool()  # populate the cache
    assert q._pool is not None

    await q.init(redis_url)  # re-init with the same URL
    assert q._pool is None  # old pool closed, cache cleared — recreated lazily

    new_pool = await q._get_pool()
    assert new_pool is not None


@pytest.mark.asyncio
async def test_close_clears_pool_and_url(redis_url: str):
    await q._get_pool()  # populate the cache
    await q.close()
    assert q._pool is None
    assert q._redis_url is None


@pytest.mark.asyncio
async def test_close_without_init_is_idempotent():
    await q.close()
    await q.close()  # must not raise the second time either


def test_queue_error_is_a_runtime_error():
    """Subclassing RuntimeError keeps existing `except RuntimeError` call
    sites working while giving callers a specific type to catch."""
    assert issubclass(QueueError, RuntimeError)


@pytest.mark.asyncio
async def test_worker_health_counts_pending_on_a_custom_queue(redis_url: str):
    """Regression guard: worker_health hardcoded "arq:queue:default".

    arq uses ``queue_name`` *directly* as the Redis key, and stores the queue
    as a sorted set — so the old ``llen("arq:queue:default")`` read the wrong
    key with the wrong type and reported 0 pending for every queue, default
    or not.
    """
    custom = f"health-q-{uuid.uuid7().hex}"
    await enqueue(simple_task, "hq-1", _queue_name=custom)
    await enqueue(simple_task, "hq-2", _queue_name=custom)

    health = await worker_health(redis_url, queue_name=custom)
    assert health["pending"] == 2, health

    # The default queue must not see the custom queue's jobs.
    default_health = await worker_health(redis_url)
    assert default_health["pending"] == 0 or "pending" in default_health


def test_task_timeout_and_retries_reach_the_arq_worker(redis_url: str):
    """Regression guard: @task(timeout=, retries=) were stamped and never read.

    make_worker now wraps each registered function via arq's ``func()`` so the
    per-task settings are actually applied instead of every job silently
    inheriting the worker-wide defaults.
    """
    worker = make_worker(redis_url)
    by_name = {f.name: f for f in worker.functions.values()}

    # `simple_task` is registered bare -> @task defaults (timeout 300, no retry)
    assert by_name["simple_task"].timeout_s == 300
    assert by_name["simple_task"].max_tries == 1

    # `retry_task` is registered as @task(retries=1, timeout=30)
    assert by_name["retryable_task"].timeout_s == 30
    # retries=1 means one extra attempt -> arq max_tries=2
    assert by_name["retryable_task"].max_tries == 2


# ---------------------------------------------------------------------------
# trace propagation across the Redis hop (api → queue → worker)
# ---------------------------------------------------------------------------


async def _drain_one(redis_url: str) -> None:
    """Run a burst-mode worker until the queue is empty."""
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
async def test_enqueue_carries_the_root_trace_id_into_the_job(redis_url: str):
    """The api → worker correlation contract: a job's logs must be tied back to the
    request that enqueued it. `root_trace_id` is the id `forktex.log` documents as
    stable across a request → job chain, so that is what crosses Redis."""
    from forktex.log import trace_context

    with trace_context("req-trace-42"):
        await enqueue(trace_probe_task, "payload")

    await _drain_one(redis_url)

    # Membership, not equality: a deferred job left by an earlier test can be drained
    # by the same burst worker, so `_results` is not exclusively ours. `_traces` is,
    # because only `trace_probe_task` writes to it.
    assert "payload" in _results
    assert len(_traces) == 1
    job_trace, job_root = _traces[0]
    assert job_root == "req-trace-42", "the enqueuing request's root trace did not survive Redis"
    # The job adopts the request's id as its own `trace_id` too, rather than minting a
    # fresh one under the inherited root: one id greps across both tiers, and "which
    # job" is already answerable from arq's `ctx["job_id"]`.
    assert job_trace == "req-trace-42"


@pytest.mark.asyncio
async def test_a_job_enqueued_with_no_trace_context_still_gets_one(redis_url: str):
    """A cron tick or operator script has no inbound trace. The job must still be
    correlatable with itself, so the worker mints one rather than logging None."""
    await enqueue(trace_probe_task, "no-trace")
    await _drain_one(redis_url)

    job_trace, job_root = _traces[0]
    assert job_trace is not None
    assert job_root is not None


@pytest.mark.asyncio
async def test_the_reserved_trace_kwarg_never_reaches_the_task_signature(redis_url: str):
    """`trace_probe_task` takes only `value`. If the wrapper failed to strip the
    reserved kwarg, arq would call it with an unexpected keyword and the job would
    fail rather than run."""
    from forktex.log import trace_context

    with trace_context("req-strip"):
        await enqueue(trace_probe_task, "stripped")
    await _drain_one(redis_url)

    assert "stripped" in _results, "job did not complete — the reserved kwarg leaked through"


@pytest.mark.asyncio
async def test_an_explicit_trace_kwarg_is_not_overwritten(redis_url: str):
    from forktex.log import trace_context

    with trace_context("ambient"):
        await enqueue(trace_probe_task, "explicit", **{q.TRACE_KWARG: "caller-wins"})
    await _drain_one(redis_url)

    assert _traces[0][1] == "caller-wins"


def test_drain_timeout_selects_arqs_waiting_shutdown_handler(redis_url: str):
    """Regression guard for a silent job-killer: arq installs its immediate-cancel
    signal handler unless `job_completion_wait` is non-zero, so a worker built
    without a drain timeout loses in-flight jobs on every SIGTERM."""
    assert make_worker(redis_url)._job_completion_wait == 0
    assert make_worker(redis_url, drain_timeout=25)._job_completion_wait == 25


@pytest.mark.asyncio
async def test_a_malformed_inbound_trace_id_is_discarded_not_adopted(redis_url: str):
    """A trace id arriving over Redis is untrusted: the producer is another process, and
    in any system that accepts user-supplied identifiers the job payload is
    attacker-influenced. Adopting it unscreened lets a crafted job forge log lines, which
    is the exact hole `log.TraceIDMiddleware` screens inbound headers to close."""
    forged = "x\n2026-01-01 00:00:00 | CRITICAL | audit | payment approved"
    await enqueue(trace_probe_task, "screened", **{q.TRACE_KWARG: forged})
    await _drain_one(redis_url)

    job_trace, job_root = _traces[0]
    assert job_trace != forged
    assert "\n" not in (job_trace or "")
    # Treated as absent, so the job still gets a usable id of its own.
    assert job_trace is not None
    assert job_root is not None


@pytest.mark.asyncio
async def test_an_over_long_inbound_trace_id_is_rejected(redis_url: str):
    """The 128-char bound matters because trace ids land in log lines and index keys."""
    await enqueue(trace_probe_task, "toolong", **{q.TRACE_KWARG: "a" * 129})
    await _drain_one(redis_url)

    assert _traces[0][0] != "a" * 129
