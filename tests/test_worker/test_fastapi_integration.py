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
from fastapi import FastAPI
from collections.abc import AsyncIterator
from collections.abc import Iterator
import asyncio
import time
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from forktex import queue
from forktex.api import AppConfig, create_app
from forktex.log import get_root_trace_id, get_trace_id
from forktex.worker import WorkerConfig, background

_observed: list[dict[str, str | None]] = []


@queue.task(queue="itest")
async def record_request(ctx: queue.JobCtx, note: str) -> str:
    _observed.append({"note": note, "trace_id": get_trace_id(), "root_trace_id": get_root_trace_id()})
    return "recorded"


def _build_app(redis_url: str) -> FastAPI:
    cfg = WorkerConfig(redis_url=redis_url, queue_name="itest", max_jobs=2, drain_timeout=5.0)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with background(cfg) as worker:
            worker.arq_worker.poll_delay_s = 0.05
            yield

    app = create_app(AppConfig(title="Integration", lifespan=lifespan))

    @app.post("/work", status_code=202)
    async def submit(note: str) -> dict[str, str]:
        job_id = await queue.enqueue(record_request, note)
        return {"jobId": job_id}

    return app


def _wait_for(predicate: Callable[[], bool], timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture(autouse=True)
def _clean(redis_url: str) -> Iterator[None]:
    _observed.clear()
    yield
    _observed.clear()


def test_an_api_consumes_its_own_queue_in_process(redis_url: str) -> None:
    with TestClient(_build_app(redis_url)) as client:
        response = client.post("/work", params={"note": "hello"})
        assert response.status_code == 202
        assert response.json()["jobId"]

        assert _wait_for(lambda: len(_observed) >= 1), "the embedded worker never ran the job"

    assert _observed[0]["note"] == "hello"


def test_the_requests_trace_id_is_visible_inside_the_job(redis_url: str) -> None:
    with TestClient(_build_app(redis_url)) as client:
        response = client.post("/work", params={"note": "traced"}, headers={"X-Request-ID": "req-integration-1"})
        assert response.headers["X-Request-ID"] == "req-integration-1"
        assert _wait_for(lambda: len(_observed) >= 1)

    assert _observed[0]["root_trace_id"] == "req-integration-1"
    assert _observed[0]["trace_id"] == "req-integration-1"


def test_the_worker_shuts_down_with_the_app(redis_url: str) -> None:
    app = _build_app(redis_url)
    with TestClient(app) as client:
        client.post("/work", params={"note": "shutdown"})
        assert _wait_for(lambda: len(_observed) >= 1)
    before = len(_observed)
    time.sleep(0.3)
    assert len(_observed) == before


def test_health_probes_can_report_the_queue_the_api_feeds(redis_url: str) -> None:

    async def queue_ready() -> bool:
        await queue.worker_health(redis_url, queue_name="itest")
        return True

    cfg = WorkerConfig(redis_url=redis_url, queue_name="itest", drain_timeout=1.0)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with background(cfg):
            yield

    app = create_app(AppConfig(lifespan=lifespan, readiness_probes={"queue": queue_ready}, readiness_timeout=5.0))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"queue": True}}


def test_an_unreachable_queue_makes_the_api_not_ready(redis_url: str) -> None:

    async def queue_ready() -> bool:
        await queue.worker_health("redis://127.0.0.1:1", queue_name="itest")
        return True

    app = create_app(AppConfig(readiness_probes={"queue": queue_ready}, readiness_timeout=3.0))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"queue": False}


def test_an_app_error_raised_while_enqueuing_still_renders_an_envelope(redis_url: str) -> None:
    app = create_app(AppConfig())

    @app.post("/broken")
    async def broken() -> dict[str, str]:
        await queue.init("redis://127.0.0.1:1")
        await queue.enqueue(record_request, "never")
        return {"unreachable": "yes"}

    with TestClient(app) as client:
        response = client.post("/broken")

    assert response.status_code >= 400
    assert "traceId" in response.json()


async def test_a_task_can_chain_more_work_from_inside_the_worker(redis_url: str) -> None:
    chained: list[str] = []

    @queue.task(queue="itest-chain")
    async def second(ctx: queue.JobCtx) -> str:
        chained.append("second")
        return "ok"

    @queue.task(queue="itest-chain")
    async def first(ctx: queue.JobCtx) -> str:
        await queue.enqueue(second)
        return "ok"

    cfg = WorkerConfig(redis_url=redis_url, queue_name="itest-chain", drain_timeout=2.0)
    async with background(cfg) as worker:
        worker.arq_worker.poll_delay_s = 0.05
        await queue.enqueue(first)
        deadline = time.monotonic() + 15
        while not chained and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

    assert chained == ["second"], "a job could not enqueue follow-up work"
