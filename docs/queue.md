# forktex.queue

arq-backed background job queue on Redis: `@task` to register, `enqueue`/`enqueue_at` to dispatch, `make_worker` to build the consumer, plus operator calls for inspection and cancellation. For durable execution with replay and state, use `flow` instead.

## Install

```bash
pip install "forktex[queue]"   # arq
```

The extra is required, but the failure is **lazy**: `import forktex.queue` succeeds without `arq`. The first call that actually needs it — `enqueue`, `enqueue_at`, `make_worker`, or any operator function that opens the pool — raises `ImportError("Install 'forktex[queue]' (arq) to use forktex.queue")`. So a service can ship the import and only discover the missing extra at first dispatch.

## Wiring

Shape A — a module-level default. `await init(redis_url)` builds a `Queue` and installs it, closing any previous handle's pool; the `ArqRedis` pool is created lazily on first use and reused for the handle's lifetime. `await close()` closes it and clears the default; it is idempotent. `Queue(redis_url)` is the same handle built directly, for a process that needs two queues or none of the global.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from forktex import queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    await queue.init("redis://redis:6379/1")
    yield
    await queue.close()


app = FastAPI(lifespan=lifespan)
```

Call `close()` in teardown. Skipping it leaks a pool bound to a dead event loop, which is the usual cause of cross-test "attached to a different loop" failures.

### Defining and dispatching tasks

```python
from datetime import UTC, datetime

from forktex.queue import JobCtx, enqueue, enqueue_at, task


@task
async def send_email(ctx: JobCtx, to: str, subject: str) -> None: ...


@task(queue="default", timeout=120, retries=3)
async def embed(ctx: JobCtx, doc_id: str) -> None: ...


job_id = await enqueue(send_email, "user@example.com", "Welcome!")
job_id = await enqueue_at(send_email, "user@example.com", "Reminder", eta=datetime(2026, 5, 9, 9, tzinfo=UTC))
```

`@task` is pure registration — it stamps the function and returns it unchanged, so it composes with other decorators (`@task` outermost, e.g. over `@traced`).

### Worker entrypoint

The one real consumer shape. Tasks reach the registry only by **side-effect import** in the entrypoint, and `make_worker(...)` must be constructed **inside the already-running event loop** — building it at module level binds arq's Redis objects to a different loop than the one that runs them. Registries in `storage`, `cache`, and `vector` are per-process, so re-register them here too.

```python
# knowledge/worker.py
import asyncio

from forktex import queue
from forktex.storage import register as register_storage


async def main() -> None:
    from knowledge.tasks import embed  # noqa: F401  side-effect: registers @task

    register_storage("default", url="http://minio:9000", bucket="kb", access_key="...", secret_key="...")
    await queue.init("redis://redis:6379/1")

    worker = queue.make_worker("redis://redis:6379/1", queue_name="default", max_jobs=8)
    try:
        await worker.async_run()
    finally:
        await queue.close()


if __name__ == "__main__":
    asyncio.run(main())
```

`init()` in the worker process matters independently of dispatch: a running task that calls `enqueue()` to chain work needs the pool. Pass `handle_signals=False` when a host (an API lifespan, a supervisor) already owns SIGTERM/SIGINT, so the host can drive shutdown itself.

## Public surface

`__all__`:

| Name | What it does |
| --- | --- |
| `task(_fn=None, *, queue="default", timeout=300, retries=0)` | Register an async function. Bare or parametrized. `retries` are *additional* attempts; `make_worker` maps them to arq's `max_tries = retries + 1`. |
| `JobCtx` | `TypedDict` for the context arq injects as the first argument: `redis`, `job_id`, `job_try`, `enqueue_time`, `score`. |
| `init(redis_url)` | Set the URL; close and drop any cached pool. |
| `close()` | Close the pool, clear the URL. Idempotent. |
| `enqueue(fn, *args, _queue_name=None, **kwargs) -> str` | Dispatch now; returns the arq job id. |
| `enqueue_at(fn, *args, eta, _queue_name=None, **kwargs) -> str` | Dispatch at `eta` (must be timezone-aware). |
| `inspect_job(job_id, *, queue_name="default") -> JobInfo \| None` | Fields: `job_id`, `status`, `function`, `args`, `kwargs`, `enqueue_time`, `start_time`, `finish_time`, `result`, `error`, `tries`. `status` is a `JobStatus`. |
| `cancel_job(job_id, *, queue_name="default") -> bool` | Signal abort, wait up to 1s for confirmation. |
| `list_jobs(queue_name="default", *, status: JobStatus \| None = None) -> list[JobInfo]` | Jobs still in the queue's sorted set (queued or deferred). |
| `worker_health(redis_url=None, *, queue_name="default") -> QueueHealth` | `pending`, `in_flight`, `failed`. |
| `make_worker(redis_url, *, queue_name="default", max_jobs=10, job_timeout=300, handle_signals=True, drain_timeout=0) -> arq.Worker` | Build a worker over every registered `@task`, with `allow_abort_jobs=True`. `drain_timeout` reaches arq as `job_completion_wait` — see the gotcha below. |
| `QueueError` | See below. |
| `DEFAULT_QUEUE` | `"default"` — the queue a bare `enqueue` and `@task` use, and arq's own default. |
| `require_default() -> Queue` | The default handle, or `QueueError`. `default()` returns `None` instead of raising. |

## Errors

| Raised | When | Catch |
| --- | --- | --- |
| `ImportError` | First use with `arq` not installed. | Deployment error; let it surface. |
| `QueueError("Queue not initialized …")` | `enqueue`/`enqueue_at`/`list_jobs`/`worker_health` before `await init(...)`. | `QueueError`, or `RuntimeError`. |
| `QueueError` | arq rejected the enqueue (deduplicated, or an unhealthy pool). | Same. |

`QueueError` subclasses **both** `AppError` (so it carries `code = AppErrorCode.INTERNAL` and renders through an `AppError` handler instead of a masked 500) and `RuntimeError` (so pre-existing `except RuntimeError` sites keep working).

## Trace correlation across the Redis hop

`enqueue`/`enqueue_at` attach the caller's `root_trace_id` to the job, and the worker
re-establishes it before the task body runs. An HTTP request that enqueues work therefore shares
one id with the job it caused, so both tiers are a single log search:

```python
from forktex.log import get_trace_id

# In a request under X-Request-ID: req-abc
await enqueue(reindex, order_id)

# Inside the job body, in the worker process:
get_trace_id()        # -> "req-abc"
```

A job enqueued with no trace context (a cron tick, an operator script) gets a freshly minted id
rather than `None`, so its own log lines are still correlatable. The carrier is a reserved job
kwarg (`queue.TRACE_KWARG`) that the worker strips before calling your function, so it never
appears in a task signature.

Two consequences worth knowing:

- The stripping happens in the wrapper `make_worker` builds. A **plain arq worker** not built by
  `make_worker` would pass the reserved kwarg straight to your function as an unexpected keyword.
- **Upgrade consumers before producers.** A worker from before this feature does not strip the
  kwarg, so jobs enqueued by a newer producer would fail on it.

## Gotchas

- **`drain_timeout=0` (the default) kills in-flight jobs on SIGTERM.** It is 0 because that is
  arq's own default, and arq installs its immediate-cancel signal handler unless the value is
  non-zero. Any worker meant to survive a rolling deploy needs a real value — set it below your
  orchestrator's grace period. [`forktex.worker`](worker.md) defaults it to 30 s for you.
- **`make_worker()` at module level breaks.** Construct it inside the running loop; a module-level instance binds arq's Redis objects to the import-time loop and fails with "attached to a different loop".
- **Registration is import-side-effect only.** If the worker entrypoint does not import the task modules, the worker starts with an empty function list and jobs sit in Redis forever. Keep the `# noqa: F401` import.
- **Registries are per-process.** `storage`, `cache`, and `vector` clients registered in the API process do not exist in the worker; re-register them before consuming.
- **`retry_delay` does not exist.** arq has no per-function retry-delay setting; an earlier version accepted the argument and silently ignored it. To control the gap between attempts, `raise arq.Retry(defer=seconds)` from the job body.
- **`queue_name` must match everywhere.** `inspect_job`/`cancel_job` default to `"default"`, but arq's own `Job` defaults to `"arq:queue"`. A mismatch makes a live job report `JobStatus.NOT_FOUND` and makes `cancel_job` return `False` regardless of its real state.
- **`cancel_job` returns `True` only for a job a worker is actively running** and confirms within 1s. A merely queued or deferred job, an already-completed one, and an unknown id all return `False`.
- **`list_jobs` cannot see running or finished jobs.** It reads the queue's sorted set, which a worker removes from on claim. It truncates at 10,000 ids with a warning — do not call it in a hot path.
- **`JobStatus` is ours, not arq's.** arq's `JobStatus` is a plain `str, Enum`, so `str()` on it is `"JobStatus.queued"`. `JobInfo.status` is a `StrEnum` of the documented values, so a filter compares equal.
- **`worker_health`'s `failed` is cumulative and worker-published.** It comes from arq's health-check key, so it is `0` until a worker has recorded health. `pending`/`in_flight` are read straight from Redis.
- **Duplicate task names overwrite.** The registry is keyed on `fn.__name__`; a second registration logs a warning and wins.
- **Reuse Redis, not the database index.** Point `queue` at a different Redis DB index than `cache` so a `FLUSHDB` on one does not take the other.
