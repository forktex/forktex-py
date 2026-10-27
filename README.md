<p align="center">
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/v/forktex.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/pyversions/forktex.svg" alt="Python"></a>
  <a href="https://github.com/forktex/forktex-py/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/forktex.svg" alt="License"></a>
</p>

<p align="center"><em>The shared Python substrate for ForkTex services.</em></p>

Fourteen modules, one library, one set of opinions. Import only what you need — each
module's third-party dependency is an optional extra, so a service that wants
structured logging never pays for Qdrant.

```bash
pip install forktex
```

> **This is not the 0.8.x `forktex`.** Up to 0.8.1 the name shipped an agentic CLI,
> which now lives in [`backlog/`](backlog/) pending republication under its own name.
> If you want the CLI, pin `forktex==0.8.1`. Pre-1.0, minor versions may break — see
> [CHANGELOG.md](CHANGELOG.md).

## Modules

**Primitives** — always available, no extra required:

| Module | What it is |
| --- | --- |
| [`log`](docs/log.md) | Structured JSON logging (Loki-ready), `trace_id` contextvar, `setup_logging` |
| [`error`](docs/error.md) | `AppError` hierarchy, `AppErrorCode`, `ErrorEnvelope`, `to_envelope` |
| [`types`](docs/types.md) | Base Pydantic models, frozen value objects, camelCase wire shapes |
| [`iso`](docs/iso.md) | Canonical ISO-8601 date/time — every datetime it returns is UTC-aware |

**Role facades** — one per piece of infrastructure:

| Module | Extra | What it is |
| --- | --- | --- |
| [`database`](docs/database.md) | — | Async Postgres/SQLAlchemy: sessions, ORM bases, CRUD, advisory locks, migrations |
| [`cache`](docs/cache.md) | — | Async Redis: `@cached`, namespaced keys, invalidation |
| [`graph`](docs/graph.md) | — | Typed multi-edge in-memory graph algebra (BFS/DFS, subgraphs) |
| [`queue`](docs/queue.md) | `[queue]` | arq background jobs: `@task`, `enqueue`, `make_worker` |
| [`storage`](docs/storage.md) | `[storage]` | S3/MinIO objects: presigned URLs, bucket lifecycle |
| [`store`](docs/store.md) | `[store]` | Schemaless documents (MongoDB) |
| [`vector`](docs/vector.md) | `[vector]` | Qdrant vector search: collections, hybrid/dense/sparse |
| [`vault`](docs/vault.md) | `[vault]` | Fernet encryption at rest, `EncryptedJSON` column type |

**Bootstrap** — process-level wiring:

| Module | Extra | What it is |
| --- | --- | --- |
| [`api`](docs/api.md) | `[api]` | FastAPI app factory: middleware stack, error envelope, health probes |
| [`worker`](docs/worker.md) | `[worker]` | Queue-consumer hosts: standalone process, embedded in a lifespan, process pool |

Install extras as needed — `pip install "forktex[storage,vector]"`, or
`pip install "forktex[all]"` for everything.

## Quick start

```python
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from forktex.database import (
    close_engine,
    create,
    get_session,
    init_engine,
    savepoint,
    session_scope,
    unmanaged_session,
    with_transactional_session,
)
from forktex.log import setup_logging

setup_logging(service="my-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine(settings.db_url, pool_pre_ping=True, pool_recycle=1800)
    yield
    await close_engine()


app = FastAPI(lifespan=lifespan)


@app.get("/projects")
async def list_projects(session: AsyncSession = Depends(session_scope)):
    ...
```

> `Depends(session_scope)` is the correct form. `get_session` is the same generator
> wrapped in `asynccontextmanager` for `async with` use in service code — passing it
> to `Depends` injects the context-manager object, not a session.

### Transactions

The outermost caller owns the transaction. Whoever opens it commits it, once, and rolls
it back on any exception:

```python
@with_transactional_session
async def place_order(session: AsyncSession, *, reference: str) -> Order:
    return await create(session, Order, reference=reference)


await place_order(reference="A-1")           # opens a session, commits it

async with get_session() as session:
    order = await place_order(session, reference="A-2")   # joins this transaction
    await add_line(session, order=order, sku="X")         # same one
    raise PaymentFailed                                   # both roll back
```

- **Handed a session, a function joins that transaction** and gets no boundary of its
  own, so it cannot half-apply.
- **`commit()`, `rollback()` and `begin()` raise `TransactionBoundaryError`** on a
  session the library opened. To abort, raise.
- **`async with savepoint(session):`** for a part allowed to fail without taking the
  rest with it — one bad row in a batch.
- **`unmanaged_session()`** for work that is deliberately many transactions, and for
  test fixtures that seed committed rows.

See [docs/database.md](docs/database.md) for the whole contract.

### No global state required

`init_engine` / `cache.init` / `queue.init` configure one process-wide default, which is
all most services want. Each is a thin shim over a handle you can build yourself —
`Database(url)`, `Cache(url)`, `Queue(url)` — so a process can hold two of them, or use
the module without the default at all.

A module whose extra is missing raises an `ImportError` that names it:

```
ImportError: Install 'forktex[vector]' (qdrant-client) to use forktex.vector
```

## Documentation

One page per module under [`docs/`](docs/), each covering install, wiring, the public
surface, the error contract, and measured gotchas.
[`docs/development.md`](docs/development.md) is the contributor guide.

## Development

```bash
make install     # poetry install --with dev --all-extras
make test        # pytest with the coverage floor
make ci          # format-check · lint · license-check · typecheck · audit · test · build · smoke
```

Integration tests run against real Postgres, Redis, MinIO, Qdrant and MongoDB via
testcontainers — Docker must be available.

## License

Dual-licensed: AGPL-3.0-or-later, or a commercial license from FORKTEX S.R.L.
(info@forktex.com). See [LICENSE](LICENSE) and [NOTICE](NOTICE).
