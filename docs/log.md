# forktex.log

Structured logging for any Python process: JSON to stdout (Loki-ready) in production, human-readable in dev, with a coroutine-scoped `trace_id` and structured extra fields carried on `contextvars`.

## Install

Always bundled — `log` is a level-0 extra with no packages behind it. `pip install forktex` is enough; `forktex[log]` resolves but installs nothing extra. Stdlib only, plus `forktex.iso` for canonical UTC timestamps. Nothing here ever raises `ImportError` for a missing extra.

## Wiring

Shape C — no global object to build or close. `setup_logging()` configures the stdlib root logger once at process startup; everything else is a plain function, context manager, or a middleware class the consumer owns.

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

`setup_logging` is idempotent — it clears `root.handlers` before installing its own. Call it once, before the app starts serving.

### TraceIDMiddleware (FastAPI / Starlette / any ASGI)

Do not hand-roll a request-id middleware; this one ships here. It is pure ASGI (no starlette or fastapi import), reads `X-Request-ID` or mints a `uuid7`, binds it for the *whole* ASGI call — endpoint, streaming body, background tasks — and echoes it on the response. An inbound header that does not match `^[A-Za-z0-9._-]{1,128}$` is rejected in favour of a minted id, so a client cannot splice `\n` into a log line.

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

Outside HTTP (workers, CLI), use `trace_context()` / `async_trace_context()` — the same primitive the middleware uses:

```python
from forktex.log import async_trace_context, get_logger

log = get_logger(__name__)


async def process_job(job_id: str) -> None:
    async with async_trace_context(f"job-{job_id}"):
        log.info("processing")   # {..."trace_id": "job-abc"}
    # restored on exit, including when the block raises
```

## Two identities: `run_id` and `trace_id`

Every record carries a **`run_id`** — one id per process invocation, minted at
`setup_logging()`. Records inside a trace scope *also* carry `trace_id` and
`root_trace_id`.

| Field | Answers | Always present? |
|:---|:---|:---|
| `run_id` | which process emitted this | **yes** |
| `trace_id` | which unit of work | only inside a scope |
| `root_trace_id` | which chain of work (request → job → child job) | only inside a scope |

`run_id` is deliberately **not** a fallback for `trace_id`. Filling an absent `trace_id`
with a process-wide value would make `trace_id=X` match thousands of unrelated records —
the appearance of correlation rather than correlation. Keeping them separate means every
line is attributable (`run_id`) while `trace_id` still means what it says.

So the honest reading of a line with no `trace_id` is "no trace scope was open here",
which for start-up lines, shutdown lines and third-party library output is the truth.
If you want those grouped, open a scope — see *Scripts, CLIs and cron* below.

## Where the trace id survives

`trace_id` and `root_trace_id` live in `ContextVar`s, so whether they cross a boundary
depends entirely on whether that boundary copies the context. This is the whole story:

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
| any subprocess (`multiprocessing`, `run_worker_pool`) | **no** | contextvars never cross a process |
| `queue.enqueue` → worker job | **yes** | carried explicitly over Redis — see [queue.md](queue.md) |

For the thread boundaries, wrap the callable with `bind_current_context`:

```python
from concurrent.futures import ThreadPoolExecutor

from forktex.log import bind_current_context

with ThreadPoolExecutor(4) as pool:
    pool.submit(bind_current_context(work), payload)
```

It captures the trace (and any `log_context()` fields) at **wrap** time and restores them
when the call runs, then restores what was there before. So wrap it in the context you
want carried — wrapping inside the worker thread captures the worker's empty context and
silently does nothing.

It resumes the same scope rather than nesting a new one, so `trace_id` is unchanged — the
thread is continuing your work, not starting a step of its own.

Prefer `asyncio.to_thread(...)` over `loop.run_in_executor(None, ...)` in async code: it
propagates the context already, so no wrapper is needed. Nothing in memory crosses a
*process* boundary — pass the id in the payload there, as `queue` does.

### Scripts, CLIs and cron

Nothing binds a trace outside an ASGI app, so a script's log lines carry no `trace_id`
unless it opens a scope itself. One scope per unit of work is the pattern:

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

Env overrides — consulted only when the matching argument is left `None`: `$FORKTEX_LOG_LEVEL`, `$FORKTEX_LOG_DEBUG`, `$FORKTEX_LOG_JSON`. An explicit argument always wins.

`JsonFormatter` / `HumanFormatter` are internal; `setup_logging` picks one for you.

### If you never call `setup_logging`

The library attaches a `NullHandler` to the `forktex` logger at import, so its own records stay silent rather than escaping to `logging.lastResort` as unformatted stderr lines. Importing does not touch the root logger — only `setup_logging` does, and it clears `root.handlers` when it runs.

An application that owns its logging keeps it and attaches `ContextFilter` instead:

```python
from forktex.log import ContextFilter

handler.addFilter(ContextFilter(service="orders"))
```

Without that filter the fields are simply absent from records, so a formatter referencing `%(trace_id)s` raises `ValueError: Formatting field not found in record`.

### JSON record shape

`timestamp` (UTC, via `iso.to_iso`), `level`, `logger`, then `service`, `message`, `run_id`, `trace_id`, `root_trace_id`, then `log_context()`/`extra={}` fields, then `exception` when `exc_info` is present. `run_id` is always present; `service`, `trace_id` and `root_trace_id` are omitted when unset. Core keys win: a colliding context field is dropped, never overwrites.

## Errors

Nothing in this module raises an error of its own. `setup_logging`, `get_logger`, the context managers and `TraceIDMiddleware` have no failure mode a caller catches; `@traced` re-raises whatever the wrapped callable raised after logging it. There is no `LogError`.

## Gotchas

- **A trace id from an untrusted source is screened, but only at the boundaries that know
  it is untrusted.** `TraceIDMiddleware` validates an inbound `X-Request-ID`, and the queue
  validates an id arriving with a job. `trace_context()` and `set_trace_id()` do **not**
  validate — they accept whatever you pass, because a caller's own id is not untrusted
  input. If you take an id from a webhook body, a CLI argument, or a message header, screen
  it yourself. `HumanFormatter` escapes control characters as a backstop so a bad id can
  corrupt at most its own line, but that is damage limitation, not validation.

- **`set_trace_id()` has no restore.** It leaves the id set for whatever runs next in that context. Prefer `trace_context()` / `async_trace_context()`, which restore in a `finally`.
- **contextvars do not cross threads or processes.** A `ThreadPoolExecutor` worker or a `multiprocessing` child starts with an empty context. Capture `get_trace_id()`/`get_extra_fields()` in the caller and re-establish them inside — there is no helper for this.
- **`queue=True` starts a listener thread that is never stopped.** `setup_logging` stays idempotent for handlers, but each call with `queue=True` starts a new `QueueListener`. Call it once.
- **Header validation is not configurable.** `TraceIDMiddleware`'s charset and 128-char cap are hardcoded; a W3C `traceparent` needs your own middleware.
- **`forktex`'s own modules log through `get_logger(__name__)`** and never call `setup_logging()`. They inherit the root handlers you configure, so their lines carry your `service`/`trace_id` too — and you can quiet them by name: `setup_logging(quiet=["forktex.database"])`.
- **Decoration order does not matter.** `@traced` resolves a logger at decoration time but stdlib logging resolves handlers and level at emit time, so importing a decorated module before `setup_logging()` is safe.
- **`handlers=[...]` replaces the transport, not the pipeline.** Your handlers still get the context filter, level, and chosen formatter applied.
