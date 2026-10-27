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

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from forktex.log import get_logger, get_root_trace_id, get_trace_id
from forktex.queue.errors import QueueError
from forktex.types import BaseAppModel

if TYPE_CHECKING:
    from types import ModuleType

    from arq import ArqRedis

logger = get_logger(__name__)

DEFAULT_QUEUE = "default"

TRACE_KWARG = "_forktex_root_trace_id"

_QUEUE_NAME_ATTR = "_queue_name"
_JOB_TIMEOUT_ATTR = "_job_timeout"
_JOB_RETRIES_ATTR = "_job_retries"

_MAX_LIST_JOBS = 10_000


class JobStatus(StrEnum):
    DEFERRED = "deferred"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    NOT_FOUND = "not_found"


class JobInfo(BaseAppModel):
    job_id: str
    status: JobStatus
    function: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    enqueue_time: datetime | None = None
    start_time: datetime | None = None
    finish_time: datetime | None = None
    result: Any = None
    error: str | None = None
    tries: int | None = None


class QueueHealth(BaseAppModel):
    pending: int
    in_flight: int
    failed: int


def _get_arq() -> ModuleType:
    try:
        import arq

        return arq
    except ImportError as exc:
        raise ImportError("Install 'forktex[queue]' (arq) to use forktex.queue") from exc


def _task_queue_name(fn: Callable) -> str:
    name = getattr(fn, _QUEUE_NAME_ATTR, DEFAULT_QUEUE)
    return name if isinstance(name, str) else DEFAULT_QUEUE


def _with_trace(kwargs: dict[str, object]) -> dict[str, object]:
    trace = get_root_trace_id() or get_trace_id()
    if trace is None or TRACE_KWARG in kwargs:
        return kwargs
    return {**kwargs, TRACE_KWARG: trace}


class Queue:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def pool(self) -> ArqRedis:
        pool = self._pool
        if pool is None:
            arq = _get_arq()
            pool = await arq.create_pool(arq.connections.RedisSettings.from_dsn(self.redis_url))
            self._pool = pool
        return pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None

    async def enqueue(self, fn: Callable, *args: object, _queue_name: str | None = None, **kwargs: object) -> str:
        pool = await self.pool()
        queue_name = _queue_name or _task_queue_name(fn)
        kwargs = _with_trace(kwargs)
        job = await pool.enqueue_job(fn.__name__, *args, _queue_name=queue_name, **cast(Any, kwargs))
        if job is None:
            raise QueueError(f"arq rejected enqueue for {fn.__name__!r} (deduplicated or pool unhealthy)")
        return job.job_id

    async def enqueue_at(
        self,
        fn: Callable,
        *args: object,
        eta: datetime,
        _queue_name: str | None = None,
        **kwargs: object,
    ) -> str:
        pool = await self.pool()
        queue_name = _queue_name or _task_queue_name(fn)
        kwargs = _with_trace(kwargs)
        job = await pool.enqueue_job(
            fn.__name__,
            *args,
            _defer_until=eta,
            _queue_name=queue_name,
            **cast(Any, kwargs),
        )
        if job is None:
            raise QueueError(f"arq rejected scheduled enqueue for {fn.__name__!r}")
        return job.job_id

    async def inspect_job(self, job_id: str, *, queue_name: str = DEFAULT_QUEUE) -> JobInfo | None:
        from arq.jobs import Job, JobResult

        pool = await self.pool()
        job = Job(job_id, pool, _queue_name=queue_name)
        info = await job.info()
        if info is None:
            return None
        status = await job.status()
        done = info if isinstance(info, JobResult) else None
        return JobInfo(
            job_id=job_id,
            status=JobStatus(status.value),
            function=info.function,
            args=info.args,
            kwargs=info.kwargs,
            enqueue_time=info.enqueue_time,
            start_time=done.start_time if done else None,
            finish_time=done.finish_time if done else None,
            result=done.result if done else None,
            error=str(done.result) if done and done.success is False else None,
            tries=info.job_try,
        )

    async def cancel_job(self, job_id: str, *, queue_name: str = DEFAULT_QUEUE) -> bool:
        from arq.jobs import Job

        pool = await self.pool()
        job = Job(job_id, pool, _queue_name=queue_name)
        try:
            return await job.abort(timeout=1)
        except TimeoutError:
            return False

    async def list_jobs(
        self,
        queue_name: str = DEFAULT_QUEUE,
        *,
        status: JobStatus | None = None,
    ) -> list[JobInfo]:
        pool = await self.pool()
        raw_ids = await pool.zrange(queue_name, 0, _MAX_LIST_JOBS - 1)
        if len(raw_ids) >= _MAX_LIST_JOBS:
            logger.warning(
                "list_jobs: truncated at %d jobs — use status filter to narrow results",
                _MAX_LIST_JOBS,
            )
        job_ids = [jid if isinstance(jid, str) else jid.decode() for jid in raw_ids]

        jobs = []
        for jid in job_ids:
            info = await self.inspect_job(jid, queue_name=queue_name)
            if info and (status is None or info.status == status):
                jobs.append(info)
        return jobs

    async def worker_health(self, *, queue_name: str = DEFAULT_QUEUE) -> QueueHealth:
        from arq.constants import health_check_key_suffix, in_progress_key_prefix

        pool: Any = await self.pool()
        return QueueHealth(
            pending=int(await pool.zcard(queue_name) or 0),
            in_flight=len(await pool.keys(f"{in_progress_key_prefix}*") or []),
            failed=_failed_count(await pool.get(f"{queue_name}{health_check_key_suffix}")),
        )


def _failed_count(raw: str | bytes | None) -> int:
    if not raw:
        return 0
    text = raw.decode() if isinstance(raw, bytes) else raw
    for field in text.split():
        key, _, value = field.partition("=")
        if key == "j_failed":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0


__all__ = ["DEFAULT_QUEUE", "TRACE_KWARG", "JobInfo", "JobStatus", "Queue", "QueueHealth"]
