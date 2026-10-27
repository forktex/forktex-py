# Changelog

All notable changes to `forktex` are documented here. This project follows
[Semantic Versioning](https://semver.org/).

Pre-1.0: minor versions may break. Pin a minor range if you need stability today.

## [Unreleased]

## [0.13.0] — 2026-10-26

`forktex.database` settles its transaction rules, and `forktex.storage` now works against any
S3-compatible server, not only MinIO.

### Breaking

- **A decorated function handed a session with no transaction of its own no longer opens
  one.** Until 0.12 the decorator called `session.begin()` in that case and committed. It
  now joins whatever the caller owns, so a caller that hands over a bare
  `sessionmaker()` or `unmanaged_session()` session and never commits **loses those
  writes silently** — the one footgun the decorator was originally written to close. Audit
  every call site that passes a session it opened itself: either open it with
  `get_session()`, which commits, or commit the `unmanaged_session()` yourself.
- **A function handed a session joins that transaction instead of opening a `SAVEPOINT`.**
  `@with_transactional_session` no longer gives a callee a boundary of its own, so a callee's
  work lands or rolls back with its caller's. Where a part must be allowed to fail on its own,
  wrap it: `async with savepoint(session): ...`, or declare the callee
  `@with_transactional_session(isolate=True)`. A batch loop that catches per-item failures needs
  one of these — without a savepoint the first failure aborts the whole transaction and every
  later statement raises `current transaction is aborted`.
- **`commit()`, `rollback()` and `begin()` raise `TransactionBoundaryError`** on a session from
  `get_session`, `session_scope` or the decorator. The boundary belongs to whoever opened it; to
  abort, raise. For work that is deliberately several transactions — a batch importer, a test
  fixture seeding committed rows — use `unmanaged_session()`, which has no boundary.
- **The decorator binds the session by parameter name**, defaulting to `session`
  (`@with_transactional_session(param="db")` to change it), instead of scanning the arguments for
  an `AsyncSession`. Nothing is shuffled out of the way for a positional call, so pass the other
  arguments by keyword. A decorated function with no such parameter raises `TypeError` at import.
- **`get_session(within=...)` and `Database.session(within=...)` are gone.** Pass the session and
  let the callee join it, or ask for a `savepoint(session)` explicitly. `Database.session(within=)`
  ignored the handle it was called on, so it was never the `Database`'s own method.

### Added

- `savepoint(session)` — an inner transaction, released on success, rolled back to on failure.
- `unmanaged_session()` and `Database.unmanaged_session()` — a session with no boundary.
- `TransactionBoundaryError`.

### Breaking — cache and queue

- **`forktex.cache.Cache` and `forktex.queue.Queue` are the handles**, holding the client
  and every operation over it. The module-level functions are unchanged in signature and are
  now shims over one default handle, as `forktex.database`'s are over one `Database`. A
  process can hold two caches or two queues, or use either without the module-level default.
- **`inspect_job`, `list_jobs` and `worker_health` return typed models** — `JobInfo`,
  `list[JobInfo]`, `QueueHealth` — instead of dicts. `list_jobs(status=...)` takes a
  `JobStatus`.

### Fixed — queue

- **`list_jobs` resolved every job's status under the default queue name**, whatever queue it
  was listing. arq reads a job's status from the sorted set it is told about, so every job on
  a non-default queue reported `not_found`.
- **`status` was never the documented vocabulary.** arq's `JobStatus` is a plain `str, Enum`,
  so `str(...)` on it yields `"JobStatus.queued"`. `inspect_job` promised `"queued"` and
  returned that, which means `list_jobs(status="queued")` had never matched a job on any
  queue. The field is now a `JobStatus`.
- `list_jobs` and `worker_health` each opened and closed a second Redis connection per call;
  they use the arq pool, which is already a Redis client.

### Breaking — storage

- **`ensure_bucket()` takes no arguments.** Declare public access once, on the client:
  `register(..., public_access="bucket-policy")`. Replace `ensure_bucket(public_read=True)`
  with that, and `ensure_bucket(public_read=False)` with a bare `ensure_bucket()`.
- **`direct_url()` raises `StorageError`** unless the bucket declares `public_access`.
  Use `presign()` for a private bucket.

### Fixed

- **Presigned URLs are SigV4.** `presign()` and `presign_post()` emitted SigV2, which MinIO
  honours and Garage, Cloudflare R2 and current AWS regions reject with 403.
- **Requests use path-style addressing.** The virtual-host form needs wildcard DNS and a
  wildcard certificate.
- **`PutBucketPolicy` is only called for `public_access="bucket-policy"`.** It is the one call
  in the module that is not plain S3; Garage answers it 501.
- **The storage test suite can start a container again.** `minio/minio` was deleted from Docker
  Hub; the suite runs against Silo, the maintained fork of the last community release.

## [0.12.0] — 2026-10-15

Session, migration, pagination and lock correctness in `forktex.database`.

### Breaking

- **`@with_transactional_session` no longer commits a session you passed in.** Your work runs
  in a savepoint and waits for your `commit()`.
- **`advisory_lock` rolls back uncommitted work** on the lock's connection when the lock is
  released. Commit inside the block.
- **Import `ConflictError` from `forktex.error`.** `forktex.database` no longer re-exports it;
  a duplicate row raises `AlreadyExistsError`.
- **Migration files must be named `v0001__description.sql`.** A misnamed file, or two files
  sharing a version number, stops the runner before anything is applied.

### Fixed

- Failed requests no longer leak database connections. A raise inside `get_session()`,
  `Database.session()` or `Depends(session_scope)` skipped the rollback and held the
  connection until garbage collection.
- A migration and its applied-record are committed together, so it cannot run twice.
- Keyset pagination works when sorting by dates, UUIDs or decimals, and no longer stops early
  at NULL sort values.
- Reading `updated_at` after an update works on models with their own `__mapper_args__`
  (raised `MissingGreenlet`).
- A lock is never returned to the pool still held.
- `ddl.AddColumn` includes the column's default.
- `AuditMixin.archived_at` is timezone-aware.

### Changed

- **One way to get a session.** `Database.session()` and `get_session()` commit on success and
  roll back on error; pass an existing session to get a savepoint inside it. `session_scope`
  and `@with_transactional_session` share that code.
- Only real model columns can be filtered or sorted on; malformed input raises
  `BadRequestError`.
- `paginate_scroll` sorts by your keyset when `order_by` is omitted, and raises `ValueError`
  on a cursor passed without its keyset.
- `UtcDateTime` and `substrate_base` are exported from `forktex.database.models`.
- `docs/database.md` rewritten as a full guide.

## [0.11.0] — 2026-08-26

### Added

- **`AppConfig` rejects unknown fields** (`extra="forbid"`). A setting a newer service passed
  to an older `forktex` was previously dropped in silence.
- **`AppConfig.api_prefix`** — mounts `create_app`'s own routes (`/health`, `/health/ready`,
  `/docs`, `/redoc`, `/openapi.json`) under a prefix, for a gateway that routes `/api/*`
  without stripping it. Defaults to `""`. A malformed value is rejected at config time.

### Changed

- **UUIDv7 everywhere**, including the worked examples and docs, which still showed `uuid4`.
- Test-suite resource names use the full `uuid7().hex` rather than a truncation. A v7 slice
  is not unique — the timestamp is front-loaded — so truncating would have collapsed
  per-run isolation.
- `test_conventions.py` enforces both halves with no allowlist: no non-v7 UUID constructor in
  `src/` or `tests/`, and no slice of a uuid-derived value.

## [0.10.0] — 2026-08-21

Ships the two process-level hosts, `api` and `worker`.

### Added

- **`forktex.api`** — `create_app(AppConfig())` returns a FastAPI instance with the
  cross-cutting stack assembled in order (security headers · CORS · trace-id · error
  envelope) plus `/health` and `/health/ready`. New `[api]` extra.
- **`forktex.worker`** — `Worker` as an object, `run_worker` as a process, `background` inside
  an async host that owns the loop, `run_worker_pool` one per OS process. New `[worker]` extra.
- **Trace correlation across the queue.** `queue.enqueue`/`enqueue_at` attach the caller's
  `root_trace_id`; the worker re-establishes it before the task body runs. The carrier is a
  reserved kwarg (`queue.TRACE_KWARG`) the worker strips.
- `queue.make_worker(..., drain_timeout=)`, `log.get_run_id()` and a `run_id` field on every
  record, `log.ContextFilter` (public), `log.bind_current_context(fn)` for the boundaries that
  do not copy contextvars (`threading.Thread`, `ThreadPoolExecutor.submit`,
  `loop.run_in_executor`), and a `NullHandler` on the `forktex` logger at import.

### Fixed

- **Workers cancelled in-flight jobs on SIGTERM.** arq installs its immediate-cancel handler
  unless `job_completion_wait` is set, and `make_worker` never set it. `forktex.worker` now
  defaults `drain_timeout` to 30 s; keep it below the orchestrator's grace period. A worker
  built with `make_worker` directly still defaults to arq's `0`.
- **A trace id could forge log lines.** A newline in an id spliced a fabricated record into
  the stream. The formatter escapes control characters, and the queue screens an inbound id
  against the same charset the middleware uses.
- **Readiness probes ran in sequence**, summing their latency. They now run concurrently under
  a per-probe `readiness_timeout`, new and defaulting to 5 s.

### Changed

- `forktex.api`'s middleware is pure ASGI, so `import forktex.api` pulls no third-party
  dependency — only `create_app` needs FastAPI.
- `worker.Worker.stop()` uses arq's `handle_sig_wait_for_completion`; `handle_sig` cancels
  in-flight tasks rather than draining.
- `worker.background()` no longer propagates arq's drain cancellation, which made a FastAPI
  lifespan's shutdown look cancelled.

### Upgrading from 0.9.0

Additive unless you use `queue`. Then: **upgrade workers before producers.** A 0.9.x worker
does not strip the reserved trace kwarg and fails the job on it. Also review `drain_timeout`
on any worker built with `make_worker` directly.

## [0.9.0] — 2026-08-16

**`forktex` ships a library, not a CLI.** Up to 0.8.1 this distribution was an agentic
software-delivery CLI; 0.9.0 replaces it with the substrate previously published as
`forktex-core`. A deliberate, breaking repurposing of the name.

### Added

Twelve modules, renamed `forktex_core.*` → `forktex.*`:

- **Primitives** — `log`, `error`, `types`, `iso`.
- **Role facades** — `database` (async Postgres/SQLAlchemy), `cache` (Redis), `queue` (arq),
  `storage` (S3/MinIO), `store` (MongoDB), `vector` (Qdrant), `vault` (Fernet at rest),
  `graph` (in-memory typed multigraph).

Every module is a declared extra. The five with third-party dependencies (`queue`, `storage`,
`store`, `vector`, `vault`) import them lazily and raise an `ImportError` naming the extra.

### Removed

- The `forktex` console script and the whole agent/CLI surface.
- The `[web]` and `[mcp]` extras.
- `forktex.graph` is **not** the old `forktex.graph`: it is the multigraph algebra, not the
  C4/architecture graph.

### Migrating

- **From `forktex` 0.8.x (the CLI):** pin `forktex==0.8.1`. 0.9.0 shares nothing with it.
- **From `forktex-core`:** rewrite `forktex_core.X` → `forktex.X` and `forktex-core[extra]` →
  `forktex[extra]`. Every public symbol keeps its name and signature, and Postgres schema
  names (`forktex_flow`, `forktex_grid`) and logging contextvar keys are unchanged.
  `forktex-core` was removed from PyPI; there is no compatibility shim.

### Notes

- Requires Python 3.14+.
- Dual-licensed: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial.
