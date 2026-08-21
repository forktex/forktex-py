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


"""Queue consumer hosts — the ``[worker]`` extra.

The mirror image of :mod:`forktex.api` for background work. :mod:`forktex.queue`
owns *what* runs (``@task``, ``enqueue``); this package owns *where a consumer
lives*:

- :class:`Worker` — the consumer as an object: an async lifecycle (startup hooks
  + queue pool) plus an awaitable ``run()``. Every host below is a thin wrapper.
- :func:`run_worker` — standalone process entrypoint. Owns ``asyncio.run`` and
  lets arq install the SIGTERM/SIGINT drain.
- :func:`background` — async context manager for a host that already owns the
  loop and the signals, e.g. an API's lifespan consuming its own queue
  in-process. Drains on exit, with a bounded fallback to cancellation.
- :func:`run_worker_pool` — one worker per OS process, for CPU-bound tasks a
  single event loop cannot parallelise. The parent supervises and forwards
  signals; it does not restart children.

The three hosts exist because signal and loop ownership belong to the host, not
to the worker.

Standalone process::

    # myservice/worker.py
    from forktex.worker import WorkerConfig, run_worker
    from myservice import tasks  # noqa: F401  side-effect registers @task

    if __name__ == "__main__":
        run_worker(WorkerConfig(redis_url="redis://localhost:6379/1"))

Inside a FastAPI app (see ``docs/worker.md`` for when this is a good idea)::

    from contextlib import asynccontextmanager

    from forktex.api import AppConfig, create_app
    from forktex.worker import WorkerConfig, background

    @asynccontextmanager
    async def lifespan(app):
        async with background(WorkerConfig(redis_url="redis://localhost:6379/1")):
            yield

    app = create_app(AppConfig(lifespan=lifespan))

What this extra does NOT do:

- **Register tasks.** Import your task modules for their side effect.
- **Restart or back off failed processes.** That is the process manager's job.

Install with ``pip install "forktex[worker]"``. Importing this package needs no
arq — only starting a worker does, and it raises ``ImportError`` naming the
``[queue]`` extra it is built on.
"""

from forktex.worker.factory import (
    DEFAULT_DRAIN_TIMEOUT,
    StartupHook,
    Worker,
    WorkerConfig,
    background,
    create_worker,
    run_worker,
    run_worker_pool,
)

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
