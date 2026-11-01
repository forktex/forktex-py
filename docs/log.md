# forktex.log

Structured logging for any Python process: JSON to stdout (Loki-ready) in production,
human-readable in dev, with a coroutine-scoped `trace_id` and extra fields on `contextvars`.

## Install

```bash
pip install forktex
```

Stdlib only. No extra required, and nothing here raises `ImportError`.

## Wiring

`setup_logging()` configures the stdlib root logger once at process startup. Everything else is a
plain function, context manager or middleware class you own.

```python
from forktex.log import setup_logging, get_logger

setup_logging(service="my-service")   # JSON, INFO, stdout
log = get_logger(__name__)
log.info("ready")
# {"timestamp":"2026-05-02T14:30:00+00:00","level":"INFO","logger":"my.module",
#  "service":"my-service","message":"ready"}

setup_logging(service="my-service", debug=True)
# 2026-05-02 14:30:00 | INFO     | my.module | ready
```

`setup_logging` is idempotent — it clears `root.handlers` first. Call it once, before serving.

### TraceIDMiddleware (FastAPI / Starlette / any ASGI)

Pure ASGI. Reads `X-Request-ID` or mints a `uuid7`, binds it for the whole ASGI call — endpoint,
streaming body, background tasks — and echoes it on the response. An inbound header not matching
`^[A-Za-z0-9._-]{1,128}$` is replaced by a minted id, so a client cannot splice `\n` into a log
line.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from forktex.log import TraceIDMiddleware, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(service="my-service")
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)                      # X-Request-ID
app.add_middleware(TraceIDMiddleware, header="X-Trace-ID")  # or another header
```

Add it before other middleware so the trace id is set first.

Outside HTTP, use `trace_context()` / `async_trace_context()`:

```python
from forktex.log import async_trace_context, get_logger

log = get_logger(__name__)


async def process_job(job_id: str) -> None:
    async with async_trace_context(f"job-{job_id}"):
        log.info("processing")   # {..."trace_id": "job-abc"}
    # restored on exit, including when the block raises
```

## Two identities: `run_id` and `trace_id`

Every record carries a `run_id`, minted once per process at `setup_logging()`. Records inside a
trace scope also carry `trace_id` and `root_trace_id`.

| Field | Answers | Always present? |
|:---|:---|:---|
| `run_id` | which process emitted this | **yes** |
| `trace_id` | which unit of work | only inside a scope |
| `root_trace_id` | which chain of work (request → job → child job) | only inside a scope |

`run_id` is not a fallback for `trace_id`: a line with no `trace_id` means no scope was open, which
is the truth for start-up, shutdown and third-party output. To group those, open a scope.

## Where the trace id survives

`trace_id` and `root_trace_id` live in `ContextVar`s, so they cross a boundary exactly when that
boundary copies the context:

| Boundary | Trace survives? | Notes |
|:---|:---|:---|
| `await` / plain call | **yes** | same context |
| `asyncio.create_task` | **yes** | task gets a copy at creation |
| `asyncio.to_thread` | **yes** | copies the context |
| FastAPI `async def` route | **yes** | `TraceIDMiddleware` binds it for the whole ASGI call |
| FastAPI `def` (sync) route or dependency | **yes** | runs in anyio's threadpool, which copies the context |
| Starlette `BackgroundTask` | **yes** | the middleware scopes the whole ASGI call, not just the response |
| `setup_logging(queue=True)` listener thread | **yes** | the context filter runs on the *emitting* side, before the record is queued |
| `threading.Thread` | **no** | a new thread starts with a fresh, empty context |
| `ThreadPoolExecutor.submit` | **no** | same reason |
| `loop.run_in_executor` | **no** | unlike `asyncio.to_thread`, it does not copy |
| any subprocess (`multiprocessing`, a process pool) | **no** | contextvars never cross a process |
| `queue.enqueue` → worker job | **yes** | carried explicitly over Redis — see [queue.md](queue.md) |

For the thread boundaries, wrap the callable with `bind_current_context`:

```python
from concurrent.futures import ThreadPoolExecutor

from forktex.log import bind_current_context

with ThreadPoolExecutor(4) as pool:
    pool.submit(bind_current_context(work), payload)
```

It captures the context at **wrap** time, so wrap it where the trace is live — wrapping inside the
worker thread captures that thread's empty context and does nothing. It resumes the same scope
rather than nesting, so `trace_id` is unchanged.

In async code prefer `asyncio.to_thread(...)` over `loop.run_in_executor(None, ...)`, which does not
copy. Nothing in memory crosses a process boundary: pass the id in the payload, as `queue` does.

### Scripts, CLIs and cron

Nothing binds a trace outside an ASGI app. Open one scope per unit of work:

```python
from forktex.log import get_logger, setup_logging, trace_context

setup_logging(service="nightly-reconcile")
log = get_logger(__name__)

for batch_id in batches:
    with trace_context(f"reconcile-{batch_id}"):
        log.info("starting")        # every line in this batch shares one id
```

## Public surface

`__all__`:

| Name | What it is |
| --- | --- |
| `setup_logging(*, service=None, level=None, debug=None, json=None, quiet=None, quiet_level=WARNING, quiet_defaults=True, fmt=None, datefmt=None, handlers=None, queue=False)` | Keyword-only. Configures the root logger; idempotent. |
| `get_logger(name)` | `logging.getLogger(name)` — one import site for the whole app. |
| `get_trace_id()` | Current trace id, or `None` when no scope is open. |
| `get_run_id()` | This process invocation's id. Always a value — never `None`. |
| `set_trace_id(value)` | Set the trace id for this context with no auto-restore. The supported way to read/write the id — the `log._context._trace_id` ContextVar is private. |
| `get_root_trace_id()` | Id established by the outermost `trace_context()`; stable across nesting. |
| `trace_context(value=None)` | Sync CM: scope a trace id, mint a `uuid7` if omitted, restore on exit. |
| `async_trace_context(value=None)` | Async counterpart. |
| `log_context(**fields)` | Sync CM: merge structured fields into every record in the block. |
| `async_log_context(**fields)` | Async counterpart (coroutine-scoped). |
| `traced(fn=None, *, name=None, level=INFO)` | Decorator, bare or parametrized, sync or async: entry line, exit line with `duration_ms`, `exception()` + re-raise on failure, inside a fresh `trace_context()`. |
| `TraceIDMiddleware` | Pure-ASGI trace-id middleware (above). |
| `DEFAULT_QUIET_LOGGERS` | The list silenced unless `quiet_defaults=False`: `uvicorn.access`, `uvicorn.error`, `sqlalchemy.engine`, `httpx`, `httpcore`, `asyncio`. |
| `get_extra_fields()` | The current `log_context()` fields as a dict (never `None`). |
| `bind_current_context(fn)` | Wrap a callable so it re-binds the calling context's trace when it later runs in a thread. |
| `ContextFilter(service=None)` | The `logging.Filter` that puts `trace_id`/`root_trace_id`/`run_id`/`service` on records. Attach it yourself when you own the handlers and cannot call `setup_logging`. |
| `shutdown_logging()` | Drain and stop the queue listener started by `setup_logging(queue=True)`. Call it on shutdown or the last records are lost. |

`$FORKTEX_LOG_LEVEL`, `$FORKTEX_LOG_DEBUG` and `$FORKTEX_LOG_JSON` are consulted only when the
matching argument is left `None`. `JsonFormatter` / `HumanFormatter` are internal.

### If you never call `setup_logging`

The library attaches a `NullHandler` to the `forktex` logger at import; importing never touches the
root logger. An application that owns its logging attaches `ContextFilter` instead:

```python
from forktex.log import ContextFilter

handler.addFilter(ContextFilter(service="orders"))
```

Without it the fields are absent, so a formatter referencing `%(trace_id)s` raises
`ValueError: Formatting field not found in record`.

### JSON record shape

`timestamp` (UTC), `level`, `logger`, `service`, `message`, `run_id`, `trace_id`, `root_trace_id`,
then `log_context()` / `extra={}` fields, then `exception` when `exc_info` is present. `service`,
`trace_id` and `root_trace_id` are omitted when unset. A colliding context field is dropped.

## Errors

Nothing here raises an error of its own. `@traced` re-raises whatever the wrapped callable raised,
after logging it.

## Gotchas

- **Only the boundaries screen an untrusted id.** `TraceIDMiddleware` validates an inbound
  `X-Request-ID` and the queue validates one arriving with a job; `trace_context()` and
  `set_trace_id()` accept whatever you pass. Screen an id taken from a webhook body, CLI argument
  or message header yourself.
- **`set_trace_id()` has no restore.** It leaves the id set for whatever runs next in that context. Prefer `trace_context()` / `async_trace_context()`, which restore in a `finally`.
- **contextvars do not cross threads or processes.** Wrap the callable with
  `bind_current_context` for a thread; pass the id in the payload for a process.
- **`queue=True` starts a listener thread per call.** `setup_logging` is idempotent for handlers but
  not for this. Call it once and `shutdown_logging()` on exit.
- **Header validation is not configurable**; a W3C `traceparent` needs your own middleware.
- **`forktex`'s own modules inherit your root handlers**, so their lines carry your
  `service`/`trace_id`. Quiet them by name: `setup_logging(quiet=["forktex.database"])`.
- **`handlers=[...]` replaces the transport, not the pipeline.** Your handlers still get the context
  filter, level and formatter.
