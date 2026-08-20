# Changelog

All notable changes to `forktex` are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
published in 0.9.0. Services depending on `forktex_core.grid` / `.flow` should stay on
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
