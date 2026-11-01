# Changelog

`forktex` follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor versions may break.

Each entry says what to change.

## [Unreleased]

## [0.14.0] — 2026-11-01

### Breaking

**`SchemaMigrationRunner` verifies what it already applied.** The version table gains a
nullable `checksum` column, added to an existing table on the next `apply()`.

- A migration whose content changed since it was applied raises `MigrationError`. A database
  never re-runs an applied migration, so the edit was never reflected and the file and the
  schema disagreed in silence.
- A pending migration numbered below the highest applied version raises `MigrationError`. It
  was applied out of order — the shape two merged branches produce — and the version table
  read as though nothing had happened.
- Rows written before this release record no checksum and are not verified, so an existing
  database keeps working. New migrations record one.


## [0.13.0] — 2026-11-01

`forktex` is eight modules and one install. The modules with no consumer, or one consumer using a
handful of names, are set aside in `backlog/facades/` with their tests and docs.

### Removed

- **`forktex.worker`**, **`forktex.graph`**, **`forktex.queue`**, **`forktex.store`**,
  **`forktex.vault`** and **`forktex.vector`**.
- Scheduled and durable work is `forktex-flow`'s job.
- **Every extra.** `forktex[x]` no longer resolves; `fastapi` and `aioboto3` are required.

### Breaking

**One install** — `import forktex` exposes `api`, `cache`, `database`, `error`, `iso`, `log`,
`storage` and `types`, each resolved on first access so one module does not import the rest.

**`forktex.database`** — [docs/database.md](docs/database.md#sessions-and-transactions)

- `get_session()` → `transactional_session()`.
- `session_scope()` → `yield_transactional_session()`.
- `unmanaged_session()` → `open_session()`. The same three renames apply on `Database`.
- `connection.engine` → `get_engine()`.
- `init_engine()` is **async** and returns `None`: `await init_engine(...)`. It disposes the engine
  it replaces, which previously leaked a live connection.
- Use `open_session()` where you used `init_engine`'s factory.
- `commit()`, `rollback()` and `begin()` raise `TransactionBoundaryError` inside
  `transactional_session` and the decorator. To abort, raise.
- `@with_transactional_session` joins the transaction of a session it is handed and never commits it.
- A decorated callee gets no `SAVEPOINT` of its own: wrap in `savepoint(session)`, or declare it
  `@with_transactional_session(isolate=True)`.
- The decorator binds the session by parameter name (`param=` to rename); pass the rest by keyword.
  A decorated function without that parameter raises `TypeError` at import.
- `within=` is gone: pass the session, or wrap in `savepoint(session)`.
- `crud.get(key=)` with an unknown column raises `BadRequestError`, not `AttributeError`.
- A cursor without its keyset raises `InvalidKeysetError`, not `ValueError`.

**`forktex.storage`** — [docs/storage.md](docs/storage.md)

- `ensure_bucket(public_read=True)` → `register(..., public_access="bucket-policy")`;
  `ensure_bucket(public_read=False)` → `ensure_bucket()`.
- `direct_url()` raises `StorageError` unless the bucket declares `public_access`; use `presign()`.
- `default()` returns `StorageClient | None` instead of raising; `require_default()` raises.

**`forktex.cache`**

- `key_for()` with a `None` part raises `InvalidCacheKeyError`, not `ValueError`.
- `init()` no longer `PING`s; call `verify()`. `Cache.connect()` → `Cache.verify()`.
- `CacheInitializationError` → `CacheUnreachableError`.

**One lifecycle on every facade** — `init` performs no I/O and releases what it replaced;
`verify()` is the explicit boot probe.

- `storage.init()` no longer verifies the bucket; call `storage.verify()`.
- `database.verify()`, `cache.verify()` and `storage.verify()` are new.
- `DatabaseUnreachableError`, `CacheUnreachableError` and `StorageUnreachableError` all carry
  `AppErrorCode.UNAVAILABLE`.

### Added

- `savepoint(session)`, `open_session()`, `get_engine()`, `TransactionBoundaryError`.
- `default()` and `require_default()` on `database`, `cache` and `storage` — one pair, one
  contract, on every facade. `default()` returns `Handle | None`; `require_default()` raises.
- `database` exports `crud`, `identifiers` and `integrity` as modules, beside `ddl`, `filters` and
  `reflect`.
- `InvalidKeysetError`, `InvalidAdvisoryKeyError`, `InvalidSchemaChangeError`, `MigrationError`,
  `InvalidCacheKeyError`.
- `StorageClient.verify()` — a `head_bucket` reachability check that creates nothing. It catches
  `BotoCoreError` as well as `ClientError`, so an unreachable endpoint no longer escapes raw.
- `Cache(url)` — an explicit handle; the module functions are shims over one default.

### Fixed

- An `AppError` whose `details` held a UUID or datetime crashed the envelope middleware, so a
  deliberate 400 reached the client as a plain-text 500 with no `traceId`.
- `storage.init()` left an unverified client registered when `verify()` failed, and `get_client()`
  kept handing it out.
- A non-positive `ttl` or `stale_ttl` now stores nothing instead of issuing the `SET … EX 0` Redis
  rejects and swallowing the error.
- `upload`, `delete`, `presign` and `presign_post` let raw botocore exceptions through, and
  `verify()` caught only `ClientError`, so an unreachable endpoint escaped unwrapped.
- A failed migration raised a raw asyncpg exception carrying driver text; it is now
  `MigrationError`, and the script and its version row roll back together.
- `eager_defaults` was dropped when `__mapper_args__` came from a mixin or a
  `@declared_attr.directive`, which is what makes reading `updated_at` after an update raise
  `MissingGreenlet`.
- `@cached` and `@traced` erased the signatures of the functions they decorated, so no call site
  was type-checked. `@with_transactional_session` now preserves the return type; it supplies the
  session parameter itself, which Python's type system cannot express, so its parameters stay open.
- A tampered cursor on a `Numeric` column raised 500 instead of `BadRequestError`.
- `presign()` emitted SigV2, which Garage, R2 and current AWS regions reject with 403.

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
