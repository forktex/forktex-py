# Changelog

`forktex` follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor versions may break.

Each entry says what to change. The reasoning lives in `docs/<module>.md`.

## [Unreleased]

## [0.13.0] — 2026-11-01

### Breaking

**`forktex.database`** — [docs/database.md](docs/database.md#sessions-and-transactions)

- `get_session()` → `transactional_session()`, `session_scope()` → `yield_transactional_session()`,
  `unmanaged_session()` → `open_session()`, and the same three on `Database`.
- `connection.engine` → `get_engine()`.
- `init_engine()` returns `None`; use `open_session()` where you used its factory.
- `commit()`, `rollback()` and `begin()` raise `TransactionBoundaryError` inside
  `transactional_session` and the decorator. To abort, raise. To own the boundary, `open_session()`.
- `@with_transactional_session` joins the transaction of a session it is handed and never commits
  it — hand it only a session something else commits, or writes are discarded at close.
- A decorated callee gets no `SAVEPOINT` of its own: wrap in `savepoint(session)`, or declare it
  `@with_transactional_session(isolate=True)`.
- The decorator binds the session by parameter name (`param=` to rename); pass the rest by keyword.
  A decorated function without that parameter raises `TypeError` at import.
- `within=` is gone: pass the session, or wrap in `savepoint(session)`.

**`forktex.storage`** — [docs/storage.md](docs/storage.md)

- `ensure_bucket(public_read=True)` → `register(..., public_access="bucket-policy")`;
  `ensure_bucket(public_read=False)` → `ensure_bucket()`.
- `direct_url()` raises `StorageError` unless the bucket declares `public_access`; use `presign()`.

**`forktex.queue`** — [docs/queue.md](docs/queue.md)

- `inspect_job`, `list_jobs` and `worker_health` return `JobInfo` / `QueueHealth`, not dicts;
  `list_jobs(status=...)` takes a `JobStatus`.

### Added

- `savepoint(session)`, `open_session()`, `get_engine()`, `TransactionBoundaryError`.
- `Cache(url)` and `Queue(url)` — explicit handles; the module functions are shims over one default.
- `WorkerError` for `forktex.worker` lifecycle misuse (also a `RuntimeError`).

### Fixed

- `list_jobs` reported every job on a non-default queue as `not_found` and its `status` filter
  matched nothing; `inspect_job` returned `"JobStatus.queued"` for `"queued"`.
- A tampered cursor on a `Numeric` column raised 500 instead of `BadRequestError`.
- `presign()` emitted SigV2, which Garage, R2 and current AWS regions reject with 403.
- `forktex.worker` raised bare `RuntimeError` before `start()`, masking as a 500.

## [0.12.0] — 2026-10-15

### Breaking

- Commit a session you pass to `@with_transactional_session` yourself.
- Commit inside an `advisory_lock` block; release rolls back uncommitted work on its connection.
- `ConflictError` moves to `forktex.error`; a duplicate row raises `AlreadyExistsError`.
- Migration files are named `v0001__description.sql`; a misnamed or duplicated version refuses to run.

### Fixed

- A raise inside a session entry point leaked the connection until garbage collection.
- A migration could run twice; it now commits with its applied-record.
- Keyset pagination stopped early at NULL sort values and mis-sorted dates, UUIDs and decimals.
- Reading `updated_at` after an update raised `MissingGreenlet` on models with own `__mapper_args__`.
- A lock could return to the pool still held; `ddl.AddColumn` dropped the column's default;
  `AuditMixin.archived_at` was naive.

### Changed

- One session shape: every entry point commits on success and rolls back on error.
- Only real model columns can be filtered or sorted on; malformed input raises `BadRequestError`.
- `paginate_scroll` sorts by your keyset when `order_by` is omitted.

## [0.11.0] — 2026-08-26

### Added

- `AppConfig` rejects unknown fields, which were previously dropped in silence.
- `AppConfig.api_prefix` mounts `create_app`'s own routes under a prefix.

### Changed

- UUIDv7 everywhere. Use the full `uuid7().hex`: a v7 slice is not unique.

## [0.10.0] — 2026-08-21

### Added

- `forktex.api` — `create_app(AppConfig())` returns a FastAPI app with the cross-cutting stack in
  order (security headers · CORS · trace-id · error envelope) and `/health`, `/health/ready`.
  New `[api]` extra.
- `forktex.worker` — `Worker`, `run_worker`, `background`, `run_worker_pool`. New `[worker]` extra.
- Trace correlation across the queue: `enqueue` carries the caller's `root_trace_id`.
- `log.get_run_id()`, a `run_id` on every record, `log.ContextFilter`, `log.bind_current_context`.

### Fixed

- Workers cancelled in-flight jobs on SIGTERM; `drain_timeout` now defaults to 30 s. Keep it below
  the orchestrator's grace period. `make_worker` directly still defaults to arq's `0`.
- A newline in a trace id spliced a fabricated record into the log stream.
- Readiness probes ran in sequence; they now run concurrently under `readiness_timeout` (5 s).

### Upgrading

Additive unless you use `queue` — then **upgrade workers before producers**: a 0.9.x worker fails
the job on the reserved trace kwarg.

## [0.9.0] — 2026-08-16

**`forktex` ships a library, not a CLI.** Up to 0.8.1 this distribution was an agentic CLI; 0.9.0
replaces it with the substrate previously published as `forktex-core`.

### Added

- Twelve modules, `forktex_core.*` → `forktex.*`: `log`, `error`, `types`, `iso`, `database`,
  `cache`, `queue`, `storage`, `store`, `vector`, `vault`, `graph`.
- Each module with a third-party dependency is an extra, imported lazily, raising an `ImportError`
  that names the extra.

### Removed

- The `forktex` console script, the whole agent/CLI surface, and the `[web]` and `[mcp]` extras.
- `forktex.graph` is the multigraph algebra, not the old C4/architecture graph.

### Upgrading

- From `forktex` 0.8.x (the CLI): pin `forktex==0.8.1`. 0.9.0 shares nothing with it.
- From `forktex-core`: rewrite `forktex_core.X` → `forktex.X` and `forktex-core[extra]` →
  `forktex[extra]`. Every public symbol keeps its name and signature; schema names and logging
  contextvar keys are unchanged. There is no compatibility shim.

Requires Python 3.14+. Dual-licensed: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial.
