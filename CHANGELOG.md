# Changelog

All notable changes to `forktex` are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.10.0] — 2026-08-21

Ships the two level-3 "bootstrap" modules — the process-level hosts — and makes them
work as one system with `queue`.

### Added

- **`forktex.api`** — FastAPI application factory. `create_app(AppConfig())` returns an
  instance with the cross-cutting stack already assembled in the correct order
  (security headers · CORS · trace-id · error envelope), plus `/health` liveness and
  `/health/ready` readiness probes. New `[api]` extra (`fastapi`).
- **`forktex.worker`** — queue-consumer hosts. `Worker` is the consumer as an object;
  `run_worker` hosts it as a process, `background` inside an async host that already owns
  the loop and signals (a FastAPI lifespan), `run_worker_pool` one per OS process for
  CPU-bound work. New `[worker]` extra (`arq`).
- **Trace correlation across the queue.** `queue.enqueue`/`enqueue_at` now attach the
  caller's `root_trace_id` to the job and the worker re-establishes it before the task
  body runs, so an HTTP request and the background work it caused share one id and are a
  single log search. A job enqueued with no trace context gets a freshly minted id
  instead of `None`. The carrier is a reserved job kwarg (`queue.TRACE_KWARG`) that the
  worker strips, so it never appears in a task signature.
- `queue.make_worker(..., drain_timeout=)` — exposes arq's `job_completion_wait`.
- **`log.get_run_id()` and a `run_id` field on every record.** One id per process
  invocation, so every line is attributable even when no trace scope was open — which
  start-up, shutdown and third-party lines never are. Deliberately a separate field
  rather than a fallback for `trace_id`: filling an absent `trace_id` with a
  process-wide value would make it match thousands of unrelated records, which is the
  appearance of correlation rather than correlation.
- **`log.ContextFilter` is public** (was `_ContextFilter`). An application that owns its
  handlers cannot call `setup_logging` — it clears `root.handlers` — and so had no way
  to get `trace_id` onto records; a formatter referencing it raised
  `ValueError: Formatting field not found in record`. The private alias still works.
- **`log.bind_current_context(fn)`** — carries the calling context's trace across the
  boundaries that do not copy contextvars (`threading.Thread`,
  `ThreadPoolExecutor.submit`, `loop.run_in_executor`). `await`,
  `asyncio.create_task`, `asyncio.to_thread` and anyio's threadpool (so FastAPI's sync
  `def` routes) already propagate and need nothing. `docs/log.md` now carries the full
  propagation table.
- **A `NullHandler` on the `forktex` logger**, attached at import. A consumer who never
  called `setup_logging` was getting the library's own records on stderr via
  `logging.lastResort`, unformatted and un-suppressible without reconfiguring the root
  logger. Importing still does not touch the root logger.

### Fixed

- **`queue` workers cancelled in-flight jobs on SIGTERM.** arq installs its
  immediate-cancel signal handler unless `job_completion_wait` is non-zero, and
  `make_worker` never set it — so every rolling restart killed work in progress. It is
  now settable via `drain_timeout`, and `forktex.worker` defaults it to 30 s. A worker
  built by `make_worker` directly still defaults to arq's `0`; set it explicitly.
  Note the flip side: a standalone worker now takes up to `drain_timeout` to exit on
  SIGTERM where it used to exit at once, so the value must sit below the orchestrator's
  grace period or the process is SIGKILLed instead of finishing cleanly.
- **A trace id could forge log lines.** `HumanFormatter` writes `trace_id` into a raw
  single-line record, so a newline in it spliced a fabricated record into the stream.
  `TraceIDMiddleware` already screened inbound `X-Request-ID` headers for exactly this
  reason, but `trace_context()` / `set_trace_id()` do not validate — so any id taken from
  a CLI argument, webhook body or message header reopened the hole. The formatter now
  escapes control characters, and the queue screens a trace id arriving with a job
  against the same charset the middleware uses, discarding a malformed one with a warning
  rather than adopting it.
- **`api`'s readiness probes ran in sequence**, making the endpoint's latency the sum of
  its dependencies. They now run concurrently, each under its own `readiness_timeout`,
  so one hung dependency is reported as failed while every other probe still reports its
  real result. The timeout is new and defaults to 5 s: a probe that legitimately takes
  longer now reports not-ready, where before it would have been awaited indefinitely.
  Raise `readiness_timeout` if you have one.

### Changed

- `forktex.api`'s middleware is pure ASGI rather than Starlette `BaseHTTPMiddleware`
  subclasses, so `import forktex.api` pulls no third-party dependency — only
  `create_app` needs FastAPI. This matches the lazy-import rule in
  `docs/development.md` and avoids `BaseHTTPMiddleware`'s known interactions with
  streaming responses and background tasks.
- `worker.Worker.stop()` calls arq's `handle_sig_wait_for_completion`, not
  `handle_sig(SIGUSR1)`. The old call mirrored arq's own `Worker.close()`, which uses
  exactly that for a `handle_signals=False` worker — so it was the idiomatic choice, not
  a careless one. It is still not a drain: `handle_sig` cancels every in-flight task,
  and `close()` then gathers the cancelled tasks. Only
  `handle_sig_wait_for_completion` stops picking up new work and waits.
- `worker.background()` no longer propagates arq's own drain cancellation. arq ends a
  drain by cancelling its main task, which made a FastAPI lifespan's shutdown look
  cancelled to the ASGI server.

### Upgrading from 0.9.0

Additive for everyone not using `queue`. If you are:

**Upgrade consumers (workers) before producers (APIs).** A 0.9.x worker does not strip
the reserved trace kwarg, so a job enqueued by a 0.10.0 producer would fail on it as an
unexpected keyword argument. Workers first, then producers, and no job is lost.

Also review `drain_timeout` on any worker built with `make_worker` directly — it still
defaults to arq's `0`, which cancels in-flight jobs on shutdown.

### Not yet included

`grid`, `flow` and `space` remain in `backlog/core/` and are **not** published. Services
depending on `forktex_core.grid` / `.flow` should stay on their current pin.

## [0.9.0] — 2026-08-16

**`forktex` now ships a library, not a CLI.** Up to 0.8.1 this distribution was an
agentic software-delivery CLI; 0.9.0 replaces it with the shared Python substrate
previously published as `forktex-core`. This is a deliberate, breaking repurposing of
the name — see *Migrating* below.

### Added

Twelve modules, moved from `forktex-core` and renamed `forktex_core.*` → `forktex.*`:

- **Primitives** — `log` (structured JSON logging, trace-id contextvar),
  `error` (`AppError` / `AppErrorCode` / `ErrorEnvelope`), `types` (base Pydantic
  models, frozen value objects), `iso` (UTC-aware ISO-8601).
- **Role facades** — `database` (async Postgres/SQLAlchemy: sessions, ORM bases, CRUD,
  keyset pagination, advisory locks, SQL-file migrations), `cache` (Redis),
  `queue` (arq), `storage` (S3/MinIO), `store` (MongoDB), `vector` (Qdrant),
  `vault` (Fernet at rest), `graph` (in-memory typed multigraph algebra).

Every module is a declared extra, so `forktex[x]` always resolves; the five with real
third-party dependencies (`queue`, `storage`, `store`, `vector`, `vault`) import them
lazily and raise an `ImportError` naming the extra.

### Removed

- The `forktex` **console script** and the entire agent/CLI surface
  (`forktex.agent`, `forktex.fsd`, `forktex.substrate`, `forktex.manual`, …).
  Preserved in `backlog/py/` pending republication under its own name.
- The `[web]` and `[mcp]` extras — both existed only for the agent's knowledge server.
- `forktex.graph` **is not the old `forktex.graph`.** The name now refers to the
  in-memory multigraph algebra from `forktex-core`, not the C4/architecture graph,
  which is in `backlog/py/graph/`.

### Not yet included

`grid`, `flow`, `space`, `api` and `worker` are in `backlog/core/` and are **not**
published in 0.9.0. (`api` and `worker` shipped in 0.10.0.) Services depending on `forktex_core.grid` / `.flow` should stay on
their current pin until those are republished.

### Migrating

**From `forktex` 0.8.x (the CLI):** pin `forktex==0.8.1`. 0.9.0 shares nothing with it.

**From `forktex-core` (any version):** rewrite `forktex_core.X` → `forktex.X`, and
`forktex-core[extra]` → `forktex[extra]`. Two things deliberately did *not* change:

- Postgres schema names (`forktex_flow`, `forktex_grid`) and the logging contextvar
  keys (`forktex_log.*`) are unchanged — renaming them would orphan deployed data.
- Every public symbol keeps its name and signature. This is a package rename, not an
  API redesign.

`forktex-core` was removed from PyPI and cannot be reinstalled; there is no
compatibility shim.

### Notes

- **Pre-1.0: the public API is not yet a stability commitment.** Minor versions may
  break until `1.0.0`. Pin `forktex>=0.9,<0.10` if you need that guarantee today.
- Requires Python 3.14+.
- Dual-licensed: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial.
