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
| `core/` | `grid/`, `flow/`, `space/`, `api/`, `worker/`, `catalog/`, `alembic.py` | Levels 2–3 of the old `forktex-core`. Deliberately out of scope for 0.9.0, which ships only primitives + role facades. |
| `tests/py/` | The CLI's 76 test entries | Follow their code. |
| `tests/core/` | `test_grid`, `test_flow`, `test_space`, `test_api`, `test_worker`, `test_catalog`, `test_stories`, `test_architecture` (the level-DAG guards), plus two files split out of surviving suites (see below) | Follow their code. |
| `client/`, `codegen/` | React Grid Studio UI + its API-client generator | Belong to `core/grid/`. |
| `docs/` | `api.md`, `flow.md`, `grid.md`, `grid-binding-design.md`, `space.md`, `worker.md`, and the CLI's own docs | Follow their code. |
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

**6. `tests/core/test_architecture/` enforces a 4-level model that no longer exists.**
`test_level_dag.py` reads levels from `core/catalog/catalog.json`, and
`test_substrate_convergence.py` keys on `levels[...] == 1`. Only
`test_public_surface.py` was kept (at `tests/test_architecture/`), rewritten to source
its package list from an explicit literal instead of the catalog.

## Known debt in the *shipped* library (not backlogged code)

Two `data-access.md` rules the published `forktex` 0.9.0 does not yet satisfy. Both predate the
migration, both are behaviour changes that deserve their own cycle, and both are recorded here so
they are not rediscovered as new findings.

**1. `database/pagination.py:keyset_predicate` builds an OR-chain, not a row-value comparison.**
`data-access.md:51-82` requires `sa.tuple_(*sort_columns) > sa.tuple_(*boundary_values)`: Postgres
compiles that to an `Index Cond` (a seek to the page boundary). The current
`sa.or_(*disjuncts)` form — `a > x OR (a = x AND id > y)` — compiles to a `Filter`, which scans from
the start of the index and degrades linearly with page depth. Correct, just slower the deeper you
page. The fix needs care: row comparison with `NULL` yields `NULL`, so it requires `NOT NULL` sort
keys or explicit `NULLS FIRST/LAST` handling, otherwise rows silently drop from results.

**2. `limit + 1` is hand-rolled at `database/crud.py:301`.**
`data-access.md:135-140` — "a shared mechanic is called, not copied". `database.pagination` owns the
cursor codec and the predicate but not the fetch-one-extra-and-truncate step, which is why the
mechanic reappeared in `crud`. The standard's own note on this: if two call sites need the same
mechanic, the shared module is incomplete — extend it rather than copying. Related trap it calls out
(`:159`): `len(rows) == limit` is the wrong `has_more` test on an exactly-full page.

## Audit findings deferred past 0.9.0

From the package-by-package audit against `../docs/engineering`. Each was verified,
judged non-blocking, and left alone deliberately — recorded so they are not
rediscovered as new findings.

**Typing erasure on decorators.** `@cached` (`cache/decorators.py`) and `@traced`
(`log/_decorators.py`) are annotated with bare `Callable`, so every decorated
function loses its signature and return type at the call site. `with_transactional_session`
(`database/connection.py`) has the same shape. The fix is `ParamSpec`/`TypeVar`
overloads on each; it is a pure typing change but touches three public decorators,
so it wants its own pass. (`cache.deserialize`'s erasure — the one that made
`response_model=` useless — was fixed in 0.9.0.)

**`dict[str, Any]` where `JsonObject` is the named type.** `python-lint.md` names
`forktex.types.JsonValue`/`JsonObject` as the replacement for a JSON boundary.
Present in `error.AppError.details`, `ErrorEnvelope.details`, `vault.encrypt`/
`decrypt`, `store`'s document parameters, and `vector`'s payloads. Note ruff's
ANN401 does **not** flag these (it targets bare `Any`), so CI passes today — this
is a consistency item, not a gate failure.

**`store._to_query_id` cannot disambiguate a 24-hex-char custom id.** A
caller-supplied string id that happens to be valid ObjectId hex is coerced to an
`ObjectId` and will never match the string it was stored as. Documented in the
function, unenforced. Fix: reject such ids at `insert_one` time, or store them
coerced.

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

**`crud._paginate_query` always issues `COUNT(*)`.** `pagination.Page` documents
`total` as opt-in "because counting is a second full predicate evaluation", and the
offset path contradicts that. Related: `crud.create` does add+flush+refresh where
`pg_insert(...).returning()` is one round trip.

**`crud.paginate_scroll` does not enforce that `keyset` matches `order_by`.** Both
module docstrings state the invariant; nothing checks it, and a disagreement
silently skips or repeats rows. `keyset` should derive `order_by`.

**`vault.encrypt` uses `json.dumps(default=str)`.** A `Decimal`/`datetime`/`UUID`
is silently stringified, so `decrypt(encrypt(x)) != x` with no error — in a
credential store round-tripping through a SQLAlchemy column. Either drop
`default=str` and fail loudly, or make the coercion the documented contract.
`cache.serialization` has the same asymmetry.

**`vault` imports `sqlalchemy` unconditionally** while gating `cryptography`
lazily, so `import forktex.vault` fails without SQLAlchemy even for a caller who
only wants `Vault`. The `[vault]` extra declares only `cryptography`.
