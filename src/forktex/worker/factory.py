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

import asyncio
import contextlib
import multiprocessing
import os
import signal
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from forktex import queue as _queue
from forktex.log import get_logger
from forktex.worker.errors import WorkerError

if TYPE_CHECKING:
    from arq.worker import Worker as ArqWorker

logger = get_logger(__name__)


StartupHook = Callable[[], Awaitable[None]]
"""Coroutine fired before the arq consumer starts. Use to register storage /
vector clients, warm caches, open pools.

Hooks run in declared order. A raising hook aborts startup — the worker does not
proceed to consume jobs unless every hook completes successfully."""

DEFAULT_DRAIN_TIMEOUT = 30.0


class WorkerConfig(BaseModel):
    redis_url: str
    queue_name: str = "default"
    max_jobs: int = 10
    job_timeout: int = 300
    drain_timeout: float = DEFAULT_DRAIN_TIMEOUT
    startup_hooks: list[StartupHook] = Field(default_factory=list)


class Worker:
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
        if self._arq is None:
            raise WorkerError("Worker.start() has not run — no arq worker yet")
        return self._arq

    async def start(self) -> None:
        if self._started:
            return
        for hook in self._config.startup_hooks:
            await hook()

        #
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
        if not self._started:
            raise WorkerError("Worker.run() before start() — use `async with Worker(...)`")
        logger.info("worker: consuming", extra={"queue": self._config.queue_name})
        await self.arq_worker.async_run()

    async def stop(self) -> None:
        if self._arq is None:
            return
        logger.info(
            "worker: draining",
            extra={"queue": self._config.queue_name, "drain_timeout": self._config.drain_timeout},
        )
        self._arq.handle_sig_wait_for_completion(signal.SIGTERM)

    async def aclose(self) -> None:
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
    return _queue.make_worker(
        redis_url=config.redis_url,
        queue_name=config.queue_name,
        max_jobs=config.max_jobs,
        job_timeout=config.job_timeout,
        drain_timeout=int(config.drain_timeout),
    )


def run_worker(config: WorkerConfig) -> None:
    asyncio.run(_bootstrap(config))


@contextlib.asynccontextmanager
async def background(
    config: WorkerConfig,
    *,
    drain_timeout: float | None = None,
) -> AsyncGenerator[Worker]:
    budget = config.drain_timeout if drain_timeout is None else drain_timeout
    worker = Worker(config, handle_signals=False)
    await worker.start()
    task = asyncio.create_task(worker.run(), name=f"forktex-worker:{config.queue_name}")
    try:
        yield worker
    finally:
        await worker.stop()
        try:
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
    if processes < 1:
        raise ValueError(f"processes must be >= 1, got {processes}")
    if processes == 1:
        run_worker(config)
        return

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


async def _bootstrap(config: WorkerConfig) -> None:
    async with Worker(config, handle_signals=True) as worker:
        await worker.run()


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
