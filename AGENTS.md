# AGENTS.md — working in this repo

`forktex` is a **library**: the shared Python substrate for ForkTex services. Twelve
modules, no CLI, no console script, no filesystem authority. If you are looking for the
agentic CLI that this distribution shipped through 0.8.1, it is in
[`backlog/py/`](backlog/) and is not built or tested here — see
[`backlog/README.md`](backlog/README.md).

## Layout

```
src/forktex/
  log/ error/ types/ iso/                        primitives — no extra required
  database/ cache/ queue/ storage/ store/
    vector/ vault/ graph/                        role facades — one per infrastructure
tests/                                           mirrors src/, one test_<pkg>/ per module
docs/                                            one page per module + development.md
backlog/                                         set aside, not built (see its README)
```

Two rules hold the shape:

- **Primitives never import a facade.** `log`/`error`/`types`/`iso` depend on each other
  at most (`types`→`iso`, `error`→`types`, `log`→`iso`) and on nothing else in the
  library. A facade may import primitives; the reverse is a layering break.
- **Facades never import each other.** They are peers over different infrastructure —
  `cache` reaching into `database` would make a service that wants Redis drag in
  Postgres. Compose them in the layer above, in your own service.

`tests/test_architecture/test_public_surface.py` enforces the public-surface half of
this (every package declares `__all__`, exports no private names, and names its extra
in the `ImportError`). The import-direction half is currently convention, not a test —
the level-DAG guard went to backlog with the 4-level model it encoded.

## Commands

```bash
make install     # poetry install --with dev --all-extras
make test        # pytest + coverage floor (94%)
make lint        # ruff check
make typecheck   # pyright, src/ only
make ci          # the full gate; run this before proposing a change is done
```

Integration tests use real Postgres, Redis, MinIO, Qdrant and MongoDB via
testcontainers — **Docker must be running**. There are no mocks for these.

## Conventions

- **Python 3.14.** PEP 695 generics (`def m[T](...)`) and PEP 758 (`except A, B:`) are
  in use. ruff targets `py314`; do not lower it — `py313` misreads both as errors.
- **Every module declares `__all__`,** and it is the contract. Adding a package means
  editing the explicit list in `test_public_surface.py` *and* adding a matching extra
  in `pyproject.toml`.
- **Optional dependencies import lazily** and raise `ImportError` naming the extra:
  `Install 'forktex[vector]' (qdrant-client) to use forktex.vector`. Never import an
  extra's package at module scope.
- **`src/` carries no lint exemptions,** `ANN401` included. A new `Any` in a signature
  is a prompt to name the type, not to add a per-file ignore.
- **Comments explain *why*.** A comment restating *what* the line does is a missing
  name; extract or rename instead.

## Things that look wrong but are not

- **`forktex_flow`, `forktex_grid`, `forktex_log.*`** appear as string literals in
  `database/migrate.py`, `database/connection.py`, `database/models.py` and
  `log/_context.py`. These are Postgres schema names and contextvar keys in deployed
  systems — **not** stale `forktex_core` references. Renaming them orphans consumer
  data.
- **The Makefile is hand-maintained.** Its generator (`forktex fsd makefile sync`) is
  in `backlog/py/fsd/` and cannot run here. Edit the Makefile directly.
- **`forktex.graph` is the in-memory multigraph algebra**, not the C4/architecture
  graph of the same name — that one is in `backlog/py/graph/`.

## Documentation

One page per module in [`docs/`](docs/): install, wiring shape, public surface, error
contract, gotchas. [`docs/development.md`](docs/development.md) is the contributor
guide and the checklist for adding a module. Keep a module's doc page in step with its
code — `test_public_surface.py` asserts every package has one.
