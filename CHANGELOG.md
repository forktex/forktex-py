# Changelog

All notable changes to `forktex` are documented here. This project follows
[Semantic Versioning](https://semver.org/).

Pre-1.0: minor versions may break. Pin a minor range if you need stability today.

Each entry says what to change. The reasoning lives in `docs/<module>.md`.

## [Unreleased]

## [0.13.0] — 2026-10-26

Transaction rules in `forktex.database`; `forktex.storage` works against any S3-compatible
server; `forktex.cache` and `forktex.queue` gain explicit handles.

### Breaking

**`forktex.database`** — see [docs/database.md](docs/database.md#sessions-and-transactions).

- Hand a decorated function only a session something will commit. It now joins the caller's
  transaction and never commits a session it was given, so a bare `sessionmaker()` or
  `unmanaged_session()` that nobody commits **loses those writes silently**. Audit every call
  site that passes a session it opened itself.
- Wrap any part that may fail on its own in `savepoint(session)`, or declare the callee
  `@with_transactional_session(isolate=True)`. A callee no longer gets its own `SAVEPOINT`, so
  a batch loop catching per-item failures needs one of these.
- Remove `commit()`, `rollback()` and `begin()` calls on a session from `get_session`,
  `session_scope`, `Database.session()` or the decorator — they raise `TransactionBoundaryError`.
  To abort, raise. For deliberately-several transactions use `unmanaged_session()`.
- Pass a decorated function's other arguments by keyword. The session binds by parameter name
  (`param="db"` to rename it), and a decorated function without that parameter raises `TypeError`
  at import.
- Replace `get_session(within=session)` and `Database.session(within=session)` with passing the
  session, or `savepoint(session)`.

**`forktex.storage`** — see [docs/storage.md](docs/storage.md).

- Replace `ensure_bucket(public_read=True)` with `register(..., public_access="bucket-policy")`,
  and `ensure_bucket(public_read=False)` with a bare `ensure_bucket()`.
- Use `presign()` for a private bucket: `direct_url()` now raises `StorageError` unless the
  bucket declares `public_access`.

**`forktex.queue`** — see [docs/queue.md](docs/queue.md).

- Read `JobInfo`, `list[JobInfo]` and `QueueHealth` attributes instead of dict keys from
  `inspect_job`, `list_jobs` and `worker_health`. `list_jobs(status=...)` takes a `JobStatus`.

### Added

- `savepoint(session)`, `unmanaged_session()`, `Database.unmanaged_session()` and
  `TransactionBoundaryError`.
- `Cache(url)` and `Queue(url)` — explicit handles holding the client and every operation over
  it. The module-level functions keep their signatures and are shims over one default handle,
  as `forktex.database`'s are over one `Database`.
- `WorkerError` for `forktex.worker`'s lifecycle misuse; it also subclasses `RuntimeError`.

### Fixed

- `list_jobs` reported every job on a non-default queue as `not_found`, and its `status` filter
  matched nothing on any queue — `inspect_job` returned `"JobStatus.queued"` where it documented
  `"queued"`.
- A tampered pagination cursor on a `Numeric` column escaped as a 500 instead of
  `BadRequestError`.
- `presign()` and `presign_post()` emitted SigV2, which Garage, Cloudflare R2 and current AWS
  regions reject with 403; requests now use path-style addressing and `PutBucketPolicy` is sent
  only for `public_access="bucket-policy"`.
- `forktex.worker` raised bare `RuntimeError` from `run()` before `start()` and from
  `arq_worker` before `start()`, which a consumer's error boundary rendered as a masked 500.
- The storage suite runs against Silo; `minio/minio` was deleted from Docker Hub.

## [0.12.0] — 2026-10-15

Session, migration, pagination and lock correctness in `forktex.database`.

### Breaking

- Commit a session you pass to `@with_transactional_session` yourself; it no longer commits one
  it was handed.
- Commit inside an `advisory_lock` block: releasing the lock rolls back uncommitted work on its
  connection.
- Import `ConflictError` from `forktex.error`; a duplicate row raises `AlreadyExistsError`.
- Name migration files `v0001__description.sql`. A misnamed file, or two sharing a version,
  stops the runner before anything is applied.

### Fixed

- A raise inside `get_session()`, `Database.session()` or `Depends(session_scope)` leaked the
  connection until garbage collection.
- A migration could run twice; it is now committed with its applied-record.
- Keyset pagination stopped early at NULL sort values and mis-sorted dates, UUIDs and decimals.
- Reading `updated_at` after an update raised `MissingGreenlet` on models with their own
  `__mapper_args__`.
- A lock could return to the pool still held; `ddl.AddColumn` dropped the column's default;
  `AuditMixin.archived_at` was naive.

### Changed

- One way to get a session: `Database.session()` and `get_session()` commit on success and roll
  back on error, and `session_scope` and `@with_transactional_session` share that code.
- Only real model columns can be filtered or sorted on; malformed input raises `BadRequestError`.
- `paginate_scroll` sorts by your keyset when `order_by` is omitted.

## [0.11.0] — 2026-08-26

### Added

- `AppConfig` rejects unknown fields, which were previously dropped in silence.
- `AppConfig.api_prefix` mounts `create_app`'s own routes under a prefix, for a gateway that
  routes `/api/*` without stripping it.

### Changed

- UUIDv7 everywhere, including the worked examples. Test resource names use the full
  `uuid7().hex`: a v7 slice is not unique, because the timestamp is front-loaded.

## [0.10.0] — 2026-08-21

Ships the two process-level hosts, `api` and `worker`.

### Added

- `forktex.api` — `create_app(AppConfig())` returns a FastAPI instance with the cross-cutting
  stack in order (security headers · CORS · trace-id · error envelope) plus `/health` and
  `/health/ready`. New `[api]` extra.
- `forktex.worker` — `Worker` as an object, `run_worker` as a process, `background` inside an
  async host, `run_worker_pool` one per OS process. New `[worker]` extra.
- Trace correlation across the queue: `enqueue`/`enqueue_at` carry the caller's `root_trace_id`
  and the worker re-establishes it before the task body runs.
- `log.get_run_id()` and a `run_id` on every record, `log.ContextFilter`, and
  `log.bind_current_context(fn)` for boundaries that do not copy contextvars.

### Fixed

- Workers cancelled in-flight jobs on SIGTERM. `forktex.worker` defaults `drain_timeout` to 30 s;
  keep it below the orchestrator's grace period. A worker built with `make_worker` directly still
  defaults to arq's `0`.
- A newline in a trace id spliced a fabricated record into the log stream.
- Readiness probes ran in sequence, summing their latency; they run concurrently under
  `readiness_timeout`, defaulting to 5 s.

### Upgrading

Additive unless you use `queue`. Then **upgrade workers before producers**: a 0.9.x worker does
not strip the reserved trace kwarg and fails the job on it.

## [0.9.0] — 2026-08-16

**`forktex` ships a library, not a CLI.** Up to 0.8.1 this distribution was an agentic
software-delivery CLI; 0.9.0 replaces it with the substrate previously published as
`forktex-core`. A deliberate, breaking repurposing of the name.

### Added

Twelve modules, renamed `forktex_core.*` → `forktex.*`: the primitives `log`, `error`, `types`,
`iso`, and the facades `database`, `cache`, `queue`, `storage`, `store`, `vector`, `vault`,
`graph`. Every module is a declared extra; the five with third-party dependencies import them
lazily and raise an `ImportError` naming the extra.

### Removed

- The `forktex` console script and the whole agent/CLI surface, and the `[web]` and `[mcp]` extras.
- `forktex.graph` is **not** the old `forktex.graph`: it is the multigraph algebra, not the
  C4/architecture graph.

### Upgrading

- **From `forktex` 0.8.x (the CLI):** pin `forktex==0.8.1`. 0.9.0 shares nothing with it.
- **From `forktex-core`:** rewrite `forktex_core.X` → `forktex.X` and `forktex-core[extra]` →
  `forktex[extra]`. Every public symbol keeps its name and signature; Postgres schema names
  (`forktex_flow`, `forktex_grid`) and logging contextvar keys are unchanged. `forktex-core` was
  removed from PyPI; there is no compatibility shim.

Requires Python 3.14+. Dual-licensed: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial.
