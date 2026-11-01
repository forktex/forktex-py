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
import re
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, TypedDict

from forktex.log import get_logger, trace_context
from forktex.queue.errors import QueueError
from forktex.queue.queue import (
    _JOB_RETRIES_ATTR,
    _JOB_TIMEOUT_ATTR,
    _QUEUE_NAME_ATTR,
    DEFAULT_QUEUE,
    TRACE_KWARG,
    JobInfo,
    JobStatus,
    Queue,
    QueueHealth,
    _get_arq,
)

if TYPE_CHECKING:
    from arq import ArqRedis
    from arq.worker import Worker

logger = get_logger(__name__)

_REDIS_SCHEMES = ("redis://", "rediss://", "unix://")

_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_registry: dict[str, Callable] = {}

_default: Queue | None = None


def default() -> Queue | None:
    return _default


def require_default() -> Queue:
    if _default is None:
        raise QueueError("Queue not initialized — call await queue.init(redis_url) first")
    return _default


async def init(redis_url: str) -> None:
    global _default
    if _default is not None:
        await _default.close()
    _default = Queue(redis_url)


async def close() -> None:
    global _default
    if _default is not None:
        await _default.close()
        _default = None


async def enqueue(fn: Callable, *args: object, _queue_name: str | None = None, **kwargs: object) -> str:
    return await require_default().enqueue(fn, *args, _queue_name=_queue_name, **kwargs)


async def enqueue_at(
    fn: Callable,
    *args: object,
    eta: datetime,
    _queue_name: str | None = None,
    **kwargs: object,
) -> str:
    return await require_default().enqueue_at(fn, *args, eta=eta, _queue_name=_queue_name, **kwargs)


async def inspect_job(job_id: str, *, queue_name: str = DEFAULT_QUEUE) -> JobInfo | None:
    return await require_default().inspect_job(job_id, queue_name=queue_name)


async def cancel_job(job_id: str, *, queue_name: str = DEFAULT_QUEUE) -> bool:
    return await require_default().cancel_job(job_id, queue_name=queue_name)


async def list_jobs(
    queue_name: str = DEFAULT_QUEUE,
    *,
    status: JobStatus | None = None,
) -> list[JobInfo]:
    return await require_default().list_jobs(queue_name, status=status)


async def worker_health(redis_url: str | None = None, *, queue_name: str = DEFAULT_QUEUE) -> QueueHealth:
    if redis_url is None:
        return await require_default().worker_health(queue_name=queue_name)
    probe = Queue(redis_url)
    try:
        return await probe.worker_health(queue_name=queue_name)
    finally:
        await probe.close()


class JobCtx(TypedDict, total=False):
    redis: ArqRedis
    job_id: str
    job_try: int
    enqueue_time: datetime
    score: float


def task(
    _fn: Callable | None = None,
    *,
    queue: str = DEFAULT_QUEUE,
    timeout: int = 300,
    retries: int = 0,
) -> Callable:

    def decorator(fn: Callable) -> Callable:
        if fn.__name__ in _registry:
            logger.warning("task %r already registered, overwriting", fn.__name__)
        _registry[fn.__name__] = fn
        setattr(fn, _QUEUE_NAME_ATTR, queue)
        setattr(fn, _JOB_TIMEOUT_ATTR, timeout)
        setattr(fn, _JOB_RETRIES_ATTR, retries)
        return fn

    if _fn is not None:
        return decorator(_fn)
    return decorator


def make_worker(
    redis_url: str,
    *,
    queue_name: str = DEFAULT_QUEUE,
    max_jobs: int = 10,
    job_timeout: int = 300,
    handle_signals: bool = True,
    drain_timeout: int = 0,
    poll_delay: float = 0.5,
) -> Worker:
    if not redis_url.startswith(_REDIS_SCHEMES):
        raise QueueError(f"redis_url must start with one of {', '.join(_REDIS_SCHEMES)}, got {redis_url!r}")
    arq = _get_arq()
    try:
        settings = arq.connections.RedisSettings.from_dsn(redis_url)
    except Exception as exc:
        raise QueueError(f"the broker at {redis_url!r} is unusable: {exc}") from exc
    return arq.Worker(
        functions=[_as_arq_function(fn) for fn in _registry.values()],
        redis_settings=settings,
        queue_name=queue_name,
        max_jobs=max_jobs,
        job_timeout=job_timeout,
        allow_abort_jobs=True,
        handle_signals=handle_signals,
        job_completion_wait=drain_timeout,
        poll_delay=poll_delay,
    )


def _as_arq_function(fn: Callable) -> object:
    from arq.worker import func

    timeout = getattr(fn, _JOB_TIMEOUT_ATTR, None)
    retries = getattr(fn, _JOB_RETRIES_ATTR, None)
    return func(
        _traced(fn),
        name=fn.__name__,
        timeout=timeout,
        max_tries=None if retries is None else retries + 1,
    )


def _traced(fn: Callable) -> Callable:

    @functools.wraps(fn)
    async def _run(ctx: JobCtx, *args: object, **kwargs: object) -> object:
        inbound = kwargs.pop(TRACE_KWARG, None)
        trace = inbound if isinstance(inbound, str) and _TRACE_ID_RE.match(inbound) else None
        if inbound is not None and trace is None:
            logger.warning(
                "queue: discarding a malformed inbound trace id",
                extra={"job": fn.__name__},
            )
        with trace_context(trace):
            return await fn(ctx, *args, **kwargs)

    return _run


__all__ = [
    "DEFAULT_QUEUE",
    "TRACE_KWARG",
    "JobCtx",
    "JobInfo",
    "JobStatus",
    "Queue",
    "QueueError",
    "QueueHealth",
    "cancel_job",
    "close",
    "default",
    "enqueue",
    "enqueue_at",
    "init",
    "inspect_job",
    "list_jobs",
    "make_worker",
    "require_default",
    "task",
    "worker_health",
]
