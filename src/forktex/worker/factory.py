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


"""The ``[worker]`` surface: a queue consumer any host can own.

The unit is :class:`Worker` — an object with an async lifecycle and an awaitable
``run()``. Everything else here is a host wrapper around it:

- :func:`run_worker` — the standalone entrypoint. Owns the process: it calls
  ``asyncio.run`` and lets arq install the signal handlers.
- :func:`background` — an async context manager for a host that already owns the
  loop and the signals (an API's lifespan, a test). Runs the consumer as a task
  and drains it on exit.
- :func:`run_worker_pool` — process-level fan-out, for CPU-bound tasks that a
  single event loop cannot parallelise.

The split exists because a single ``run_worker`` that owns ``asyncio.run`` *and*
lets arq claim SIGTERM/SIGINT can only ever be a process entrypoint — an API
that wants to consume its own queue in-process has no way in. Signal ownership
is a property of the host, not of the config, so it is a :class:`Worker`
constructor argument rather than a :class:`WorkerConfig` field.
"""

from __future__ import annotations

import asyncio
import contextlib
import multiprocessing
import os
import signal
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from forktex import queue as _queue
from forktex.log import get_logger

if TYPE_CHECKING:
    from arq.worker import Worker as ArqWorker

logger = get_logger(__name__)


StartupHook = Callable[[], Awaitable[None]]
"""Coroutine fired before the arq consumer starts. Use to register storage /
vector clients, warm caches, open pools.

Hooks run in declared order. A raising hook aborts startup — the worker does not
proceed to consume jobs unless every hook completes successfully."""

#: Default seconds to let in-flight jobs finish before giving up on a graceful stop.
DEFAULT_DRAIN_TIMEOUT = 30.0


class WorkerConfig(BaseModel):
    """Inputs to :class:`Worker` and the host wrappers."""

    redis_url: str
    queue_name: str = "default"
    max_jobs: int = 10
    job_timeout: int = 300
    #: Seconds to let in-flight jobs finish on shutdown. Reaches arq as
    #: ``job_completion_wait``, which is what selects its draining signal handler
    #: over the immediate-cancel one — at 0, a SIGTERM kills running jobs. Set this
    #: below your orchestrator's grace period so the drain completes first.
    drain_timeout: float = DEFAULT_DRAIN_TIMEOUT
    startup_hooks: list[StartupHook] = Field(default_factory=list)


class Worker:
    """A queue consumer with an explicit lifecycle.

    Use as an async context manager, then await :meth:`run`::

        async with Worker(config, handle_signals=False) as worker:
            await worker.run()

    ``__aenter__`` runs the startup hooks and initialises the queue pool;
    ``__aexit__`` closes the arq worker and the pool. Entering is what makes the
    consumer usable — :meth:`run` on an unstarted worker raises rather than
    silently consuming with half-wired dependencies.
    """

    def __init__(self, config: WorkerConfig, *, handle_signals: bool = True) -> None:
        self._config = config
        self._handle_signals = handle_signals
        self._arq: ArqWorker | None = None
        self._started = False

    @property
    def config(self) -> WorkerConfig:
        return self._config

    @property
    def arq_worker(self) -> ArqWorker:
        """The underlying arq worker. Available only after :meth:`start`."""
        if self._arq is None:
            raise RuntimeError("Worker.start() has not run — no arq worker yet")
        return self._arq

    async def start(self) -> None:
        """Run startup hooks, initialise the queue pool, build the arq worker."""
        if self._started:
            return
        # Hooks first, so anything they register (storage clients, DB pools) is
        # ready before a single job is consumed.
        for hook in self._config.startup_hooks:
            await hook()

        # The module-level pool lets a running @task call `enqueue()` to chain work,
        # so a job can dispatch follow-up work instead of silently dropping it.
        #
        # Note this is NOT a reachability check: `queue.init` only records the URL and
        # opens no socket, so a wrong host gets past it and surfaces later, when arq
        # first connects to consume. Verifying the broker here would mean an extra
        # round-trip that also turns "Redis is not up yet" into a failed start, which
        # is a deployment-visible choice and not this function's to make.
        try:
            await _queue.init(self._config.redis_url)
        except Exception:
            logger.exception("worker: queue.init failed — aborting startup")
            raise

        self._arq = _queue.make_worker(
            redis_url=self._config.redis_url,
            queue_name=self._config.queue_name,
            max_jobs=self._config.max_jobs,
            job_timeout=self._config.job_timeout,
            handle_signals=self._handle_signals,
            # int() because arq compares this against a whole-second budget.
            drain_timeout=int(self._config.drain_timeout),
        )
        self._started = True
        logger.info(
            "worker: ready",
            extra={
                "queue": self._config.queue_name,
                "max_jobs": self._config.max_jobs,
                "handle_signals": self._handle_signals,
                "drain_timeout": self._config.drain_timeout,
            },
        )

    async def run(self) -> None:
        """Consume jobs until stopped, cancelled, or (if it owns them) signalled."""
        if not self._started:
            raise RuntimeError("Worker.run() before start() — use `async with Worker(...)`")
        logger.info("worker: consuming", extra={"queue": self._config.queue_name})
        await self.arq_worker.async_run()

    async def stop(self) -> None:
        """Stop picking up new jobs and let in-flight ones finish.

        Safe to call from a signal handler or another task; a no-op if the worker
        never started. Returns as soon as the drain has been *requested* — await
        :meth:`run` (or use :func:`background`) to know when it finished.

        Uses arq's ``handle_sig_wait_for_completion``, **not** ``handle_sig``. The
        latter is what arq's own ``Worker.close()`` calls for a
        ``handle_signals=False`` worker, so it is the idiomatic choice — but it is not a
        drain: it cancels every in-flight task, and ``close()`` then gathers the
        cancelled tasks. Only ``handle_sig_wait_for_completion`` stops picking up new
        work and waits. Do not "simplify" this back.

        The wait budget is the ``drain_timeout`` handed to arq as
        ``job_completion_wait`` in :meth:`start`.
        """
        if self._arq is None:
            return
        logger.info(
            "worker: draining",
            extra={"queue": self._config.queue_name, "drain_timeout": self._config.drain_timeout},
        )
        # A plain method call, not a real signal delivery — arq takes the signal
        # only to name it in its own shutdown log line.
        self._arq.handle_sig_wait_for_completion(signal.SIGTERM)

    async def aclose(self) -> None:
        """Close the arq worker and the queue pool. Idempotent."""
        if self._arq is not None:
            with contextlib.suppress(Exception):
                await self._arq.close()
            self._arq = None
        with contextlib.suppress(Exception):
            await _queue.close()
        self._started = False

    async def __aenter__(self) -> Worker:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


def create_worker(config: WorkerConfig) -> ArqWorker:
    """Build a configured ``arq.Worker`` ready to consume jobs.

    Returns the bare arq worker with no lifecycle wiring — no startup hooks and
    no queue pool. Prefer :class:`Worker` (or :func:`run_worker`), which own
    both; this stays for callers handing a worker to arq's own CLI.
    """
    return _queue.make_worker(
        redis_url=config.redis_url,
        queue_name=config.queue_name,
        max_jobs=config.max_jobs,
        job_timeout=config.job_timeout,
        drain_timeout=int(config.drain_timeout),
    )


async def _bootstrap(config: WorkerConfig) -> None:
    """Async portion of :func:`run_worker` — a pure coroutine, for testability."""
    async with Worker(config, handle_signals=True) as worker:
        await worker.run()


def run_worker(config: WorkerConfig) -> None:
    """One-shot bootstrap: hooks → queue init → consume, until signalled.

    Owns the process: it calls ``asyncio.run`` and lets arq install the
    SIGTERM/SIGINT drain. Use from a worker entrypoint script::

        # myservice/worker.py
        from forktex.worker import WorkerConfig, run_worker
        from myservice import tasks  # noqa  side-effect: register @task

        if __name__ == "__main__":
            run_worker(WorkerConfig(redis_url="redis://localhost:6379/1"))

    Inside a host that already owns the loop, use :func:`background` instead.
    """
    asyncio.run(_bootstrap(config))


@contextlib.asynccontextmanager
async def background(
    config: WorkerConfig,
    *,
    drain_timeout: float | None = None,
) -> AsyncIterator[Worker]:
    """Run the consumer alongside a host that owns the loop and the signals.

    Yields the started :class:`Worker` while it consumes in a background task,
    then asks it to drain and waits up to ``drain_timeout`` (defaulting to the
    config's) before cancelling. The host keeps its own signal handling — arq's
    are not installed.

    Note the two budgets: this one bounds how long *we* wait, while arq's own drain
    is bounded by ``config.drain_timeout``. Passing a smaller value here makes this
    the effective limit; passing a larger one leaves arq's the effective limit.

    In a FastAPI lifespan::

        @asynccontextmanager
        async def lifespan(app):
            async with background(WorkerConfig(redis_url=...)):
                yield

    A worker task that dies on its own does not take the host down silently: the
    exception is logged and re-raised on exit.
    """
    budget = config.drain_timeout if drain_timeout is None else drain_timeout
    worker = Worker(config, handle_signals=False)
    await worker.start()
    task = asyncio.create_task(worker.run(), name=f"forktex-worker:{config.queue_name}")
    try:
        yield worker
    finally:
        await worker.stop()
        try:
            # `asyncio.wait` rather than `wait_for(shield(...))`: arq ends its own
            # drain by cancelling its main task, so `run()` legitimately finishes
            # *cancelled*. `wait_for` would re-raise that CancelledError and, from
            # inside a lifespan's shutdown, make the whole ASGI app look cancelled.
            # `wait` reports completion without propagating either outcome, leaving
            # us to tell an expected cancellation from a real crash below.
            done, _pending = await asyncio.wait({task}, timeout=budget)
            if not done:
                logger.warning(
                    "worker: drain timed out — cancelling in-flight jobs",
                    extra={"queue": config.queue_name, "drain_timeout": budget},
                )
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            elif not task.cancelled() and (exc := task.exception()) is not None:
                logger.exception(
                    "worker: consumer task failed",
                    exc_info=exc,
                    extra={"queue": config.queue_name},
                )
                raise exc
        finally:
            await worker.aclose()


def run_worker_pool(config: WorkerConfig, *, processes: int = 1) -> None:
    """Run ``processes`` independent workers, one per OS process.

    A single :func:`run_worker` is one event loop, so it parallelises *waiting*
    but not computing — CPU-bound tasks serialise behind the GIL no matter how
    high ``max_jobs`` goes. This is the escape hatch: each child is a full
    :func:`run_worker`, so they share nothing but the queue.

    The parent is a supervisor only. It forwards SIGTERM/SIGINT to the children
    and waits for them to drain; it does not restart them, because a crash-loop
    is the process manager's job to see and to back off from.

    Because children are spawned (not forked), ``config`` is **pickled** to reach
    them — so every ``startup_hooks`` entry must be a module-level function. A
    lambda or a closure raises a pickling error here while working fine in
    :func:`run_worker` and :func:`background`.
    """
    if processes < 1:
        raise ValueError(f"processes must be >= 1, got {processes}")
    if processes == 1:
        # No supervisor for a pool of one: an extra process would only add a
        # signal hop between the manager and the worker.
        run_worker(config)
        return

    # "spawn" rather than the Linux default "fork": the parent may already hold
    # an event loop, Redis sockets or a database pool, none of which survive a
    # fork intact.
    ctx = multiprocessing.get_context("spawn")
    children = [ctx.Process(target=run_worker, args=(config,), name=f"forktex-worker-{i}") for i in range(processes)]
    for child in children:
        child.start()
    logger.info(
        "worker: pool started",
        extra={"queue": config.queue_name, "processes": processes, "pids": [c.pid for c in children]},
    )

    stopping = False

    def _forward(signum: int, _frame: object) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        logger.info("worker: pool stopping", extra={"signal": signal.Signals(signum).name})
        for child in children:
            if child.pid is not None and child.is_alive():
                with contextlib.suppress(ProcessLookupError):
                    os.kill(child.pid, signal.SIGTERM)

    previous = {sig: signal.signal(sig, _forward) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for child in children:
            child.join()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    exit_codes = {child.name: child.exitcode for child in children}
    logger.info("worker: pool stopped", extra={"queue": config.queue_name, "exit_codes": exit_codes})


__all__ = [
    "DEFAULT_DRAIN_TIMEOUT",
    "StartupHook",
    "Worker",
    "WorkerConfig",
    "background",
    "create_worker",
    "run_worker",
    "run_worker_pool",
]
