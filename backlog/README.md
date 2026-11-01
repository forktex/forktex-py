# backlog/

Code that is **set aside, not deleted**. Nothing here is built, tested, linted,
type-checked, or published — it is excluded from the wheel and sdist
(`exclude = ["backlog/**"]`), from pytest (`norecursedirs`), from ruff and pyright
(`exclude`), and from the license-header check (`SKIP_DIRS`).

It is expected to return, package by package, in later cycles.

## What is here

| Path | What | Why it is here |
| --- | --- | --- |
| `py/` | The `forktex` agent CLI — `agent/` (21.7k LOC), `fsd/`, `graph/` (C4), `grid/`, `substrate/`, `runtime/`, `manual/`, `manifest/`, `core/`, `api/`, `models/`, `filesystem/`, `architecture/`, `engineering/`, `cloud/`, `network/`, `data/`, `intelligence/`, `config.py` | The `forktex` distribution was repurposed to publish the primitives library. The CLI needs its own name before it can ship again. |
| `core/` | `grid/`, `flow/`, `space/`, `catalog/`, `alembic.py` | Level 2 of the old `forktex-core`, plus the catalog. Out of scope for 0.9.0, which shipped primitives + role facades. (Level 3 — `api/` and `worker/` — has since been promoted; see below.) |
| `tests/py/` | The CLI's 76 test entries | Follow their code. |
| `tests/core/` | `test_grid`, `test_flow`, `test_space`, `test_catalog`, `test_stories`, `test_architecture` (the level-DAG guards), plus two files split out of surviving suites (see below) | Follow their code. |
| `client/`, `codegen/` | React Grid Studio UI + its API-client generator | Belong to `core/grid/`. |
| `docs/` | `graph.md`, `queue.md`, `store.md`, `vault.md`, `vector.md` for the parked facades; `flow.md`, `grid.md`, `grid-binding-design.md`, `space.md` and the CLI's own docs | Follow their code. |
| `facades/` | `graph/`, `queue/`, `store/`, `vault/`, `vector/` | Set aside for 0.13.0. `graph` and `store` had no consumer anywhere in the fleet; `queue`, `vault` and `vector` had one each, using 2-5 of their exported names, and their defects clustered in the surface nobody called. Parking them dropped `arq`, `pymongo`, `cryptography` and `qdrant-client`. |
| `tests/facades/` | `test_graph`, `test_queue`, `test_store`, `test_vault`, `test_vector` | Follow their code. All five ran against real containers; `store`'s needed a Mongo replica set. |
| `README-agent-cli.md`, `CHANGELOG-agent-cli.md` | The CLI's README and changelog | Preserved verbatim; the repo root now documents the library. |

## Landmines — read before reviving anything

**1. `forktex.graph` is taken.** `src/forktex/graph/` is now the in-memory multigraph
algebra from `forktex-core` (686 LOC). The C4/architecture graph (3,862 LOC) is at
`backlog/py/graph/`. `backlog/py/{architecture,manual,agent}` all import
`forktex.graph` meaning the *C4* one. Reviving them requires renaming one of the two —
`forktex.archgraph` for the C4 graph is the obvious call — not just moving files back.

**2. Never rename the Postgres schema literals.** `forktex_flow` and `forktex_grid`
(in `core/flow/persist/models.py`, `core/grid/persist/models.py`, and the `*.sql`
migrations) are **physical schema names in deployed consumer databases**. They look
like stale `forktex_core` references. They are not. Renaming them to match the new
package name orphans every consumer's data. Same for the `forktex_log.*` contextvar
keys in `src/forktex/log/_context.py`.

**3. `fractal` does not exist anywhere.** `py/agent/knowledge/` (9 modules) imports
`forktex_core.fractal`, which was only ever in the deleted `forktex-core` 2.x PyPI
lineage — it is in neither this repo nor the old core-py source tree. The old pin
`forktex-core[fractal]>=2.4.0,<3.0.0` is unresolvable. Restoring the knowledge
subsystem means first deciding: reimplement fractal, or rebuild it on `grid`/`vector`.

**4. The FSD tooling generates this repo's Makefile.** `py/fsd/` provides
`forktex fsd makefile sync`, which produced the Makefile at the repo root. With `fsd/`
backlogged that generator cannot run here, so the **Makefile is now hand-maintained**
and its header says so. No `forktex.json` remains at the root — the declarative record
went to backlog/ with the generator. Reviving `fsd/` means re-authoring it and
re-establishing generation.

**5. Two test files were split, not moved wholesale.**
`tests/core/test_temporal_standard_grid.py` and `tests/core/test_iso_grid_temporal.py`
were carved out of `tests/test_database/test_temporal_standard.py` and
`tests/test_iso/test_iso.py` — the halves that assert grid's behaviour. Fold them back
into their original suites (or into grid's own) when grid returns; do not restore them
as standalone files.

**6. Level 3 has been promoted — do not restore it from git history.** `core/api/`,
`core/worker/`, their tests and their docs were deleted here and now live under
`src/forktex/{api,worker}/`, `tests/test_{api,worker}/` and `docs/{api,worker}.md`. Neither is
a straight copy, and reviving the old files would undo real fixes:

- `api`'s middleware is pure ASGI instead of `BaseHTTPMiddleware` subclasses, so
  `import forktex.api` needs no FastAPI; readiness probes now run concurrently under a
  per-probe timeout.
- `worker.Worker.stop()` now calls arq's `handle_sig_wait_for_completion`, not `handle_sig`.
  The old code's comment claimed `handle_sig(SIGUSR1)` was arq's drain path; it is arq's
  *immediate-cancel* path, so a graceful stop silently killed in-flight jobs.
- `background()` no longer re-raises arq's own drain cancellation, which used to make a
  FastAPI lifespan's shutdown look cancelled.

Only `grid/`, `flow/`, `space/` and `catalog/` remain out of the box.

**7. `tests/core/test_architecture/` enforces a 4-level model that no longer exists.**
`test_level_dag.py` reads levels from `core/catalog/catalog.json`, and
`test_substrate_convergence.py` keys on `levels[...] == 1`. Only
`test_public_surface.py` was kept (at `tests/test_architecture/`), rewritten to source
its package list from an explicit literal instead of the catalog.

## Debt in the shipped library

Verified, judged non-blocking, left alone deliberately — recorded so they are not
rediscovered as new findings.

**`database/pagination.py:keyset_predicate` builds an OR-chain, not a row-value comparison.**
`database:keyset-row-comparison` (`database-design.json`) requires `sa.tuple_(*sort_columns) > sa.tuple_(*boundary_values)`: Postgres
compiles that to an `Index Cond` (a seek to the page boundary). The current
`sa.or_(*disjuncts)` form — `a > x OR (a = x AND id > y)` — compiles to a `Filter`, which scans from
the start of the index and degrades linearly with page depth. Correct, just slower the deeper you
page. The fix needs care: row comparison with `NULL` yields `NULL`, so it requires `NOT NULL` sort
keys or explicit `NULLS FIRST/LAST` handling, otherwise rows silently drop from results.

**`limit + 1` is hand-rolled in `database/crud.py`.** `reuse:extend-the-shared-module`
(`code-reuse.json`): when two call sites re-implement the same step next to a module that owns the
rest of that concern, the module is extended. `database.pagination` owns the cursor codec and the
predicate but not the fetch-one-extra-and-truncate step, which is why it reappeared in `crud`.

**`crud._paginate_query` always issues `COUNT(*)`.** `pagination.Page` documents
`total` as opt-in "because counting is a second full predicate evaluation", and the
offset path contradicts that. Related: `crud.create` does add+flush+refresh where
`pg_insert(...).returning()` is one round trip.

## Fix before reviving a parked facade

**`store._to_query_id` cannot disambiguate a 24-hex-char custom id.** A
caller-supplied string id that happens to be valid ObjectId hex is coerced to an
`ObjectId` and will never match the string it was stored as, so `insert_one`
returns an id that can never fetch, update or delete the row. Verified against a
live MongoDB. **Fix this before `store/` returns**: coerce symmetrically on
insert, or stop coercing on read.

**`vector` reads `SearchQuery`'s private attributes across modules.**
`collection.py` reaches into `query._vector`/`._limit`/`._strategy`/
`._payload_filter`/`._score_threshold`/`._sparse_vector`. Inside one package, but
it is the "depending on private internals" anti-pattern. Fix: frozen public fields
or a `to_request()` method.

**`graph`'s lazily-built index goes stale on direct mutation.** `Graph.nodes` and
`Graph.edges` are public mutable lists beside an index guarded by `_indexed`, which
only ever rebuilds once — appending directly after a read leaves `has_node`
answering `False` for a present node. Fix: read-only properties, or a dirty flag.
Also `dfs`/`cycles` recurse without a depth guard.

**`vault` has no known-answer test**, so nothing in the repository pins the
output of `_derive_fernet_key`. A change to it would stay green and silently
orphan every credential already encrypted at rest. Add a fixed-KEK /
fixed-ciphertext / expected-plaintext vector before `vault/` returns. Also:
`Vault(kek="")` is accepted and derives `sha256(b"")`, a publicly computable key,
and `tests/facades/test_vault/test_vault.py` asserts that as correct.

**`vault`'s key handling blocks its own biggest consumer.** It SHA-256s whatever
it is handed, while `cloud` generates a raw Fernet key and passes it straight to
`Fernet(...)` in seven hand-rolled places. The two are therefore key-incompatible:
adopting `forktex.vault` in `cloud` is a data migration, not an import. Decide
whether `Vault` should accept an already-valid 32-byte urlsafe-b64 key verbatim.

**`vault.encrypt` uses `json.dumps(default=str)`.** A `Decimal`/`datetime`/`UUID`
is silently stringified, so `decrypt(encrypt(x)) != x` with no error — in a
credential store round-tripping through a SQLAlchemy column. Either drop
`default=str` and fail loudly, or make the coercion the documented contract.
`cache.serialization` stringifies the same way, but its round-trip is symmetric: a
`@cached` miss returns what a hit would.

**`vault` imports `sqlalchemy` unconditionally** while gating `cryptography`
lazily, so `import forktex.vault` fails without SQLAlchemy even for a caller who
only wants `Vault`. The `[vault]` extra declares only `cryptography`.

## Driver gotchas for the parked facades

Carried over from `docs/development.md` when `queue`, `vector`, `store`, `vault` and `graph`
were set aside. Each cost a debugging session; none is discoverable from the driver's docs.

### Qdrant: point IDs

Point IDs must be unsigned integers or UUID strings; an arbitrary string is a 400. Use `int` or
`str(uuid.uuid7())`.

### Qdrant: `AsyncQdrantClient` has no `async with`

The `AsyncQdrantClient` in qdrant-client ≥ 1.14 does not implement `__aenter__`/`__aexit__`. Use explicit `try/finally` + `await q.close()`.

### arq 0.28 API changes

- `arq.worker.WorkerSettings` doesn't exist — use `arq.Worker` directly
- `arq.Job` doesn't exist at the top level — use `arq.jobs.Job`
- `Worker.async_run()` for programmatic burst mode; `arq` CLI uses `arq module.WorkerSettings`
