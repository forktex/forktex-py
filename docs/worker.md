# forktex.worker

The host a queue consumer runs in: a standalone process, a consumer inside an API's lifespan, or
one worker per CPU. [`queue`](queue.md) owns *what* runs (`@task`, `enqueue`).

## Install

```bash
pip install "forktex[worker]"
```

The extra declares `arq`, the same dependency as `[queue]`. Starting a worker raises
`ImportError: Install 'forktex[queue]' (arq)` if it is missing.

## Wiring

Build a `WorkerConfig` and hand it to one of three hosts. They differ in who owns the event loop
and the signals.

| Host | Owns the loop? | Owns SIGTERM? | Use for |
|:---|:---|:---|:---|
| `run_worker(config)` | yes (`asyncio.run`) | arq does | a dedicated worker process |
| `background(config)` | no — the host does | the host does | a consumer inside an API lifespan |
| `run_worker_pool(config, processes=N)` | one per child | parent forwards | CPU-bound tasks |

### Standalone process

```python
# myservice/worker.py
from forktex.worker import WorkerConfig, run_worker
from myservice import tasks  # noqa: F401  — import side-effect registers @task

if __name__ == "__main__":
    run_worker(WorkerConfig(redis_url="redis://localhost:6379/1", queue_name="default"))
```

Nothing registers your tasks. Import the module that defines them, for its side effect.

### Startup hooks

Hooks run in declared order before the first job is consumed; a raising hook aborts startup.

```python
from forktex.database import init_engine
from forktex.storage import register
from forktex.worker import WorkerConfig, run_worker


async def open_pools() -> None:
    init_engine(settings.db_url)
    register("uploads", endpoint=settings.s3_url)


run_worker(WorkerConfig(redis_url=settings.redis_url, startup_hooks=[open_pools]))
```

`Worker.start` initialises the `queue` pool too, so a running job can `enqueue()` follow-up work.
It does **not** verify the broker is reachable: a wrong `redis_url` surfaces when arq first
connects, not at startup.

### Process pool

One worker is one event loop: it parallelises waiting, not computing, so CPU-bound tasks serialise
behind the GIL however high `max_jobs` goes.

```python
run_worker_pool(WorkerConfig(redis_url=settings.redis_url, max_jobs=4), processes=4)
```

The parent forwards SIGTERM/SIGINT and waits for children to drain. It does **not** restart them.

## Draining

`drain_timeout` reaches arq as `job_completion_wait`, which selects arq's draining signal handler
over its immediate-cancel one. At arq's own default of `0`, a SIGTERM cancels running jobs, so
every rolling deploy kills work in progress; `forktex.worker` defaults it to `30.0` seconds.

Set it below your orchestrator's grace period:

```yaml
# Kubernetes: give the pod more room than the worker needs.
terminationGracePeriodSeconds: 45    # >  drain_timeout
```

```python
WorkerConfig(redis_url=..., drain_timeout=30.0)
```

`Worker.stop()` requests the drain and returns. Awaiting `run()`, or leaving `background()`, is
what tells you it finished.

## Public surface

| Name | Purpose |
|:---|:---|
| `WorkerConfig` | The configuration model |
| `Worker` | The consumer as an object: `start` / `run` / `stop` / `aclose`, or `async with` |
| `run_worker(config)` | Standalone process entrypoint |
| `background(config)` | Async context manager for an embedded consumer |
| `run_worker_pool(config, processes=N)` | One worker per OS process |
| `create_worker(config)` | A bare `arq.Worker` with no lifecycle wiring, for arq's own CLI |
| `StartupHook` | The startup-hook callable type |
| `DEFAULT_DRAIN_TIMEOUT` | `30.0` |

### `WorkerConfig`

| Field | Default | Effect |
|:---|:---|:---|
| `redis_url` | — (required) | Broker URL |
| `queue_name` | `"default"` | Must match `@task(queue=...)` and the producer's `enqueue` |
| `max_jobs` | `10` | Concurrent jobs in one event loop |
| `job_timeout` | `300` | Seconds before a job is killed |
| `drain_timeout` | `30.0` | Graceful-stop budget — see above |
| `startup_hooks` | `[]` | Coroutines run in order before consuming |

## Errors

| Raised | When | Catch? |
|---|---|---|
| `ImportError("Install 'forktex[queue]' (arq) to use forktex.queue")` | arq is not installed. | No — install the extra. |
| `WorkerError` | `run()` before `start()`, or `arq_worker` before `start()`. Subclasses `AppError` (code `INTERNAL`) and `RuntimeError`, so `except RuntimeError` still works and a transport can render it. | No — a lifecycle mistake. |

Task failures are arq's: use `@task(retries=...)` and `queue.inspect_job`.

## Gotchas

- **Nothing registers your tasks.** Import the module that defines them.
- **`queue_name` must agree across all three sides** — `@task(queue=...)`, `enqueue`, and
  `WorkerConfig.queue_name`. A mismatch is silent: jobs queue and nothing consumes them.
- **`run_worker_pool` pickles the config**, because children are spawned, not forked. Every
  `startup_hooks` entry must be a module-level function — a lambda or a closure fails here while
  working fine in `run_worker` and `background`.
- `create_worker` skips the hooks and the queue pool. Prefer `Worker`.
- A `background()` consumer that dies on its own re-raises on exit.

---

## Running a worker inside a FastAPI app

`background()` puts the consumer in the API's lifespan, with [`api`](api.md):

```python
from contextlib import asynccontextmanager

from forktex.api import AppConfig, create_app
from forktex.database import close_engine, init_engine
from forktex.log import setup_logging
from forktex.queue import enqueue, task, worker_health
from forktex.worker import WorkerConfig, background

setup_logging(service="orders")

WORKER = WorkerConfig(redis_url=settings.redis_url, queue_name="orders", drain_timeout=20.0)


@task(queue="orders")
async def reindex_order(ctx, order_id: str) -> None:
    ...


async def queue_ready() -> bool:
    await worker_health(settings.redis_url, queue_name="orders")
    return True


@asynccontextmanager
async def lifespan(app):
    init_engine(settings.db_url)
    async with background(WORKER):        # consumer starts here, drains on exit
        yield
    await close_engine()


app = create_app(
    AppConfig(
        title="Orders",
        lifespan=lifespan,
        readiness_probes={"queue": queue_ready},
    )
)


@app.post("/orders/{order_id}/reindex", status_code=202)
async def reindex(order_id: str) -> dict[str, str]:
    return {"jobId": await enqueue(reindex_order, order_id)}
```

### One trace id across both tiers

`enqueue` attaches the caller's `root_trace_id` and the worker re-establishes it before the task
body runs, so the id returned in `X-Request-ID` is the id the job logs under:

```
{"level":"INFO","message":"reindex accepted","trace_id":"req-abc","root_trace_id":"req-abc"}
{"level":"INFO","message":"reindexing","trace_id":"req-abc","root_trace_id":"req-abc"}   ← the job
```

A job enqueued with no trace context gets a freshly minted id. The carrier is a reserved job
kwarg the worker strips, so it never appears in a task signature.

### When *not* to embed the worker

- **Shared fate.** An OOM from a heavy job kills the process serving HTTP.
- **Shared CPU.** A busy job starves the event loop and inflates request latency.
- **Coupled scaling.** Request capacity and job capacity cannot scale apart.
- **Multiplied consumers.** `N` API replicas is `N` consumers, and `max_jobs` is per-process, so
  total concurrency is `N × max_jobs`.

Embed for a single-replica service or local development. Split as soon as either tier needs to
scale or fail on its own — same `WorkerConfig`, `run_worker` in its own entrypoint.
