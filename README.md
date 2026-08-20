<p align="center">
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/v/forktex.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/pyversions/forktex.svg" alt="Python"></a>
  <a href="https://github.com/forktex/forktex-py/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/forktex.svg" alt="License"></a>
</p>

<p align="center"><em>The shared Python substrate for ForkTex services.</em></p>

Twelve modules, one library, one set of opinions. Import only what you need — each
module's third-party dependency is an optional extra, so a service that wants
structured logging never pays for Qdrant.

> **`forktex` 0.9.0 is a different package from `forktex` 0.8.x.** Up to 0.8.1 this
> name shipped an agentic CLI. That tool now lives in [`backlog/`](backlog/) pending
> republication under its own name. If you want the CLI, pin `forktex==0.8.1`.

```bash
pip install forktex
```

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

Install extras as needed — `pip install "forktex[storage,vector]"`, or
`pip install "forktex[all]"` for everything.

## Quick start

```python
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from forktex.database import close_engine, init_engine, session_scope
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
> to `Depends` injects the context-manager object, not a session. See
> [docs/database.md](docs/database.md).

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
