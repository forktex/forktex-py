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

from collections.abc import Coroutine
from collections.abc import Callable
from typing import Any
from collections.abc import Iterator
import asyncio
import signal

import pytest

from forktex import queue
from forktex.worker import (
    DEFAULT_DRAIN_TIMEOUT,
    Worker,
    WorkerConfig,
    background,
    create_worker,
    run_worker,
    run_worker_pool,
)
from forktex.worker.factory import _bootstrap


@pytest.fixture(autouse=True)
def _register_dummy_task() -> Iterator[None]:

    @queue.task()
    async def _noop(ctx: dict) -> str:
        return "ok"

    yield


class _FakeArq:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.signals: list[int] = []
        self.graceful: list[int] = []
        self._stop = asyncio.Event()

    async def async_run(self) -> None:
        self.calls.append("run")
        await self._stop.wait()
        self.calls.append("returned")

    def handle_sig(self, signum: int) -> None:
        self.signals.append(signum)
        self._stop.set()

    def handle_sig_wait_for_completion(self, signum: int) -> None:
        self.graceful.append(signum)
        self._stop.set()

    async def close(self) -> None:
        self.calls.append("close")


@pytest.fixture
def fake_arq(monkeypatch: pytest.MonkeyPatch) -> _FakeArq:
    from forktex.worker import factory as worker_factory

    built: dict = {}
    fake = _FakeArq()

    def _make_worker(**kwargs: object) -> _FakeArq:
        built.update(kwargs)
        return fake

    monkeypatch.setattr(worker_factory._queue, "make_worker", _make_worker)
    fake.built = built
    return fake


@pytest.fixture
def no_queue_io(monkeypatch: pytest.MonkeyPatch) -> None:
    from forktex.worker import factory as worker_factory

    async def _noop(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(worker_factory._queue, "init", _noop)
    monkeypatch.setattr(worker_factory._queue, "close", _noop)


def test_worker_config_defaults() -> None:
    cfg = WorkerConfig(redis_url="redis://localhost:6379/1")
    assert cfg.queue_name == "default"
    assert cfg.max_jobs == 10
    assert cfg.job_timeout == 300
    assert cfg.drain_timeout == DEFAULT_DRAIN_TIMEOUT
    assert cfg.startup_hooks == []


def test_config_reaches_the_arq_worker(fake_arq: _FakeArq, no_queue_io: None) -> None:
    cfg = WorkerConfig(redis_url="redis://h/1", queue_name="q", max_jobs=3, job_timeout=7, drain_timeout=11.0)

    async def _go() -> None:
        async with Worker(cfg):
            pass

    asyncio.run(_go())
    built = fake_arq.built
    assert built["queue_name"] == "q"
    assert built["max_jobs"] == 3
    assert built["job_timeout"] == 7
    assert built["drain_timeout"] == 11


def test_drain_timeout_reaches_arq_as_an_int(fake_arq: _FakeArq, no_queue_io: None) -> None:

    async def _go() -> None:
        async with Worker(WorkerConfig(redis_url="redis://h/1", drain_timeout=2.9)):
            pass

    asyncio.run(_go())
    assert fake_arq.built["drain_timeout"] == 2
    assert isinstance(fake_arq.built["drain_timeout"], int)


async def test_start_runs_hooks_in_order_before_the_queue_pool(
    fake_arq: _FakeArq, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forktex.worker import factory as worker_factory

    order: list[str] = []

    async def hook_a() -> None:
        order.append("a")

    async def hook_b() -> None:
        order.append("b")

    async def _init(*_a: object, **_k: object) -> None:
        order.append("queue.init")

    async def _close(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(worker_factory._queue, "init", _init)
    monkeypatch.setattr(worker_factory._queue, "close", _close)

    cfg = WorkerConfig(redis_url="redis://h/1", startup_hooks=[hook_a, hook_b])
    async with Worker(cfg):
        pass

    assert order == ["a", "b", "queue.init"]


async def test_a_raising_hook_aborts_before_any_consuming(fake_arq: _FakeArq, no_queue_io: None) -> None:
    async def boom() -> None:
        raise RuntimeError("hook failed")

    cfg = WorkerConfig(redis_url="redis://h/1", startup_hooks=[boom])
    worker = Worker(cfg)
    with pytest.raises(RuntimeError, match="hook failed"):
        await worker.start()

    assert fake_arq.calls == [], "the consumer started despite a failed hook"


async def test_run_before_start_is_refused() -> None:
    worker = Worker(WorkerConfig(redis_url="redis://h/1"))
    with pytest.raises(RuntimeError, match="before start"):
        await worker.run()


async def test_arq_worker_property_before_start_is_refused() -> None:
    worker = Worker(WorkerConfig(redis_url="redis://h/1"))
    with pytest.raises(RuntimeError, match="has not run"):
        _ = worker.arq_worker


async def test_start_is_idempotent(fake_arq: _FakeArq, no_queue_io: None) -> None:
    worker = Worker(WorkerConfig(redis_url="redis://h/1"))
    await worker.start()
    first = worker.arq_worker
    await worker.start()
    assert worker.arq_worker is first
    await worker.aclose()


async def test_standalone_owns_the_signals_and_embedded_does_not(fake_arq: _FakeArq, no_queue_io: None) -> None:
    cfg = WorkerConfig(redis_url="redis://h/1")

    async with Worker(cfg, handle_signals=True):
        pass
    assert fake_arq.built["handle_signals"] is True

    async with Worker(cfg, handle_signals=False):
        pass
    assert fake_arq.built["handle_signals"] is False


async def test_stop_and_aclose_are_safe_before_start(fake_arq: _FakeArq) -> None:
    worker = Worker(WorkerConfig(redis_url="redis://h/1"))
    await worker.stop()
    await worker.aclose()


async def test_aclose_is_idempotent(fake_arq: _FakeArq, no_queue_io: None) -> None:
    worker = Worker(WorkerConfig(redis_url="redis://h/1"))
    await worker.start()
    await worker.aclose()
    await worker.aclose()
    assert fake_arq.calls.count("close") == 1


async def test_stop_drains_instead_of_cancelling_in_flight_jobs(fake_arq: _FakeArq, no_queue_io: None) -> None:
    worker = Worker(WorkerConfig(redis_url="redis://h/1"), handle_signals=False)
    await worker.start()
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)
    await worker.stop()
    await task

    assert fake_arq.graceful == [signal.SIGTERM]
    assert fake_arq.signals == [], "stop() went through arq's immediate-cancel path"
    await worker.aclose()


async def test_stop_makes_run_return(fake_arq: _FakeArq, no_queue_io: None) -> None:
    worker = Worker(WorkerConfig(redis_url="redis://h/1"), handle_signals=False)
    await worker.start()
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)
    await worker.stop()
    await asyncio.wait_for(task, timeout=1)
    assert fake_arq.calls == ["run", "returned"]
    await worker.aclose()


async def test_background_consumes_alongside_the_host_and_drains(fake_arq: _FakeArq, no_queue_io: None) -> None:
    cfg = WorkerConfig(redis_url="redis://h/1")
    async with background(cfg) as worker:
        assert isinstance(worker, Worker)
        await asyncio.sleep(0)
        assert "run" in fake_arq.calls

    assert fake_arq.graceful == [signal.SIGTERM]
    assert "returned" in fake_arq.calls
    assert "close" in fake_arq.calls


async def test_background_does_not_let_arq_take_the_hosts_signals(fake_arq: _FakeArq, no_queue_io: None) -> None:
    async with background(WorkerConfig(redis_url="redis://h/1")):
        pass
    assert fake_arq.built["handle_signals"] is False


async def test_background_cancels_when_the_drain_overruns(no_queue_io: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from forktex.worker import factory as worker_factory

    class _NeverStops:
        def __init__(self) -> None:
            self.cancelled = False

        async def async_run(self) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

        def handle_sig_wait_for_completion(self, signum: int) -> None:
            pass

        async def close(self) -> None:
            pass

    stubborn = _NeverStops()
    monkeypatch.setattr(worker_factory._queue, "make_worker", lambda **_k: stubborn)

    cfg = WorkerConfig(redis_url="redis://h/1", drain_timeout=0.05)
    async with background(cfg):
        await asyncio.sleep(0)

    assert stubborn.cancelled, "an unresponsive consumer was never cancelled"


async def test_background_uses_an_explicit_drain_timeout_over_the_config(
    no_queue_io: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forktex.worker import factory as worker_factory

    class _NeverStops:
        def __init__(self) -> None:
            self.cancelled = False

        async def async_run(self) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

        def handle_sig_wait_for_completion(self, signum: int) -> None:
            pass

        async def close(self) -> None:
            pass

    stubborn = _NeverStops()
    monkeypatch.setattr(worker_factory._queue, "make_worker", lambda **_k: stubborn)

    cfg = WorkerConfig(redis_url="redis://h/1", drain_timeout=300.0)
    async with background(cfg, drain_timeout=0.05):
        await asyncio.sleep(0)

    assert stubborn.cancelled


async def test_background_reraises_a_consumer_that_dies_on_its_own(
    no_queue_io: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forktex.worker import factory as worker_factory

    class _Dies:
        async def async_run(self) -> None:
            raise RuntimeError("consumer exploded")

        def handle_sig_wait_for_completion(self, signum: int) -> None:
            pass

        async def close(self) -> None:
            pass

    monkeypatch.setattr(worker_factory._queue, "make_worker", lambda **_k: _Dies())

    with pytest.raises(RuntimeError, match="consumer exploded"):
        async with background(WorkerConfig(redis_url="redis://h/1")):
            await asyncio.sleep(0)


def test_run_worker_is_a_thin_asyncio_run_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    from forktex.worker import factory as worker_factory

    seen: dict = {}

    def _fake_run(coro: Coroutine[Any, Any, object]) -> None:
        seen["coro"] = coro.__qualname__
        coro.close()

    monkeypatch.setattr(worker_factory.asyncio, "run", _fake_run)
    run_worker(WorkerConfig(redis_url="redis://h/1"))
    assert seen["coro"] == _bootstrap.__qualname__


def test_a_pool_of_one_skips_the_supervisor(monkeypatch: pytest.MonkeyPatch) -> None:
    from forktex.worker import factory as worker_factory

    calls: list[str] = []
    monkeypatch.setattr(worker_factory, "run_worker", lambda cfg: calls.append("direct"))

    def _no_process(*_a: object, **_k: object) -> None:
        raise AssertionError("a pool of one spawned a supervisor")

    monkeypatch.setattr(worker_factory.multiprocessing, "get_context", _no_process)
    run_worker_pool(WorkerConfig(redis_url="redis://h/1"), processes=1)
    assert calls == ["direct"]


def test_a_pool_needs_at_least_one_process() -> None:
    with pytest.raises(ValueError, match="processes must be >= 1"):
        run_worker_pool(WorkerConfig(redis_url="redis://h/1"), processes=0)


def test_create_worker_passes_through_to_queue(fake_arq: _FakeArq) -> None:
    cfg = WorkerConfig(redis_url="redis://h/1", queue_name="passthrough", drain_timeout=9.0)
    create_worker(cfg)
    assert fake_arq.built["queue_name"] == "passthrough"
    assert fake_arq.built["drain_timeout"] == 9
    assert "handle_signals" not in fake_arq.built


class _FakeChild:
    def __init__(
        self,
        target: Callable[..., object] | None = None,
        args: tuple[object, ...] = (),
        name: str = "",
    ) -> None:
        self.name = name
        self.pid = 4242
        self.exitcode = 0
        self.started = False
        self.joined = False

    def start(self) -> None:
        self.started = True

    def join(self) -> None:
        self.joined = True

    def is_alive(self) -> bool:
        return False


@pytest.fixture
def fake_pool(monkeypatch: pytest.MonkeyPatch) -> list[_FakeChild]:
    from forktex.worker import factory as worker_factory

    made: list[_FakeChild] = []

    class _Ctx:
        def Process(self, **kwargs: object) -> _FakeChild:
            child = _FakeChild(**kwargs)
            made.append(child)
            return child

    def _get_context(method: str) -> _Ctx:
        assert method == "spawn", f"pool must spawn, not {method!r}"
        return _Ctx()

    monkeypatch.setattr(worker_factory.multiprocessing, "get_context", _get_context)
    return made


def test_a_pool_starts_and_joins_one_process_per_worker(fake_pool: list[_FakeChild]) -> None:
    run_worker_pool(WorkerConfig(redis_url="redis://h/1"), processes=3)
    assert len(fake_pool) == 3
    assert all(c.started and c.joined for c in fake_pool)


def test_a_pool_uses_spawn_not_fork(fake_pool: list[_FakeChild]) -> None:
    run_worker_pool(WorkerConfig(redis_url="redis://h/1"), processes=2)
    assert len(fake_pool) == 2


def test_the_pool_restores_the_signal_handlers_it_installed(fake_pool: list[_FakeChild]) -> None:
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    run_worker_pool(WorkerConfig(redis_url="redis://h/1"), processes=2)
    after = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    assert after == before


async def test_arqs_own_drain_cancellation_is_not_mistaken_for_the_host_stopping(
    no_queue_io: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forktex.worker import factory as worker_factory

    class _CancelsItselfOnDrain:
        def __init__(self) -> None:
            self._task: asyncio.Task | None = None

        async def async_run(self) -> None:
            self._task = asyncio.current_task()
            await asyncio.Event().wait()

        def handle_sig_wait_for_completion(self, signum: int) -> None:
            assert self._task is not None
            self._task.cancel()

        async def close(self) -> None:
            pass

    monkeypatch.setattr(worker_factory._queue, "make_worker", lambda **_k: _CancelsItselfOnDrain())

    async with background(WorkerConfig(redis_url="redis://h/1", drain_timeout=5.0)):
        await asyncio.sleep(0)


def test_config_is_exposed_on_the_worker() -> None:
    cfg = WorkerConfig(redis_url="redis://h/1", queue_name="exposed")
    assert Worker(cfg).config is cfg


def test_the_pool_forwards_a_signal_to_every_live_child(
    fake_pool: list[_FakeChild], monkeypatch: pytest.MonkeyPatch
) -> None:
    from forktex.worker import factory as worker_factory

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(worker_factory.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    handlers: dict = {}
    real_signal = signal.signal

    def _capture(sig: int, handler: object) -> None:
        if callable(handler):
            handlers[sig] = handler
        return real_signal(sig, handler) if not callable(handler) else real_signal(sig, signal.SIG_DFL)

    monkeypatch.setattr(worker_factory.signal, "signal", _capture)

    monkeypatch.setattr(_FakeChild, "is_alive", lambda self: True)

    run_worker_pool(WorkerConfig(redis_url="redis://h/1"), processes=2)

    forward = handlers[signal.SIGTERM]
    forward(signal.SIGTERM, None)
    assert killed == [(4242, signal.SIGTERM), (4242, signal.SIGTERM)]

    forward(signal.SIGTERM, None)
    assert len(killed) == 2
