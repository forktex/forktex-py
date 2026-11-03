# Changelog

`forktex` follows [Semantic Versioning](https://semver.org/): every name in a module's `__all__` is
covered.

## [Unreleased]

## [1.0.0] — 2026-11-03

First stable release. Requires Python 3.14, SQLAlchemy 2.1, asyncpg 0.32, redis-py 8.1, pydantic 2.14, FastAPI 0.162 and aioboto3 15.5 or newer.

- `forktex.log`: structured JSON logging with `run_id` and a `trace_id` that follows requests, tasks and threads (`trace_context`, `log_context`, `bind_current_context`, `@traced`, `TraceIDMiddleware`).
- `forktex.error`: the `AppError` hierarchy, the `AppErrorCode` vocabulary and the `ErrorEnvelope` wire shape.
- `forktex.types`: `BaseAppModel` (camelCase on the wire), `BaseValueObject` and `BaseWireValueObject` (frozen), `UtcDateTime`, `UtcDate` and the JSON type aliases.
- `forktex.iso`: UTC datetime and date conversion to and from ISO-8601 text.
- `forktex.database`: async PostgreSQL on SQLAlchemy with `transaction()` and `session()`, ORM bases and mixins, CRUD, offset and keyset pagination, client filters, advisory locks, typed constraint errors and `SchemaMigrationRunner`.
- In a FastAPI route, `Depends(transaction.dependency, scope="function")` commits before the response is sent.
- `forktex.cache`: async Redis with `get`/`set`/`delete`, `@cached` with stale-while-revalidate, `key_for` and prefix invalidation.
- `forktex.storage`: S3-compatible objects with upload, download, existence checks, presigned GET and PUT URLs, browser POST policies and named clients.
- `forktex.api`: `create_app` with error envelopes, trace ids, security headers, CORS and liveness and readiness probes.
- Each infrastructure module has a process-wide default (`default()`, `require_default()`, `verify()`) and handle classes (`Database`, `Cache`, `StorageClient`) for more than one.
