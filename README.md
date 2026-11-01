<p align="center">
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/v/forktex.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/pyversions/forktex.svg" alt="Python"></a>
  <a href="https://github.com/forktex/forktex-py/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/forktex.svg" alt="License"></a>
</p>

<p align="center"><em>The shared Python substrate for ForkTex services.</em></p>

One install, no extras: `import forktex` resolves every module.

```bash
pip install forktex
```

> **This is not the 0.8.x `forktex`**, which was an agentic CLI — for that, pin
> `forktex==0.8.1`. Pre-1.0, minor versions may break; see [CHANGELOG.md](CHANGELOG.md).

## Modules

**Primitives**

| Module | What it is |
| --- | --- |
| [`log`](docs/log.md) | Structured JSON logging (Loki-ready), `trace_id` contextvar, `setup_logging` |
| [`error`](docs/error.md) | `AppError` hierarchy, `AppErrorCode`, `ErrorEnvelope`, `to_envelope` |
| [`types`](docs/types.md) | Base Pydantic models, frozen value objects, camelCase wire shapes |
| [`iso`](docs/iso.md) | Canonical ISO-8601 date/time — every datetime it returns is UTC-aware |

**Role facades** — one per piece of infrastructure:

| Module | What it is |
| --- | --- |
| [`database`](docs/database.md) | Async Postgres/SQLAlchemy: sessions, ORM bases, CRUD, advisory locks, migrations |
| [`cache`](docs/cache.md) | Async Redis: `@cached`, namespaced keys, invalidation |
| [`storage`](docs/storage.md) | S3/MinIO objects: presigned URLs, bucket lifecycle |

**Bootstrap** — process-level wiring:

| Module | What it is |
| --- | --- |
| [`api`](docs/api.md) | FastAPI app factory: middleware stack, error envelope, health probes |

`graph`, `queue`, `store`, `vault` and `vector` are set aside in
`backlog/facades/` until a consumer needs them.

## Quick start

```python
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from forktex.database import close_engine, init_engine, yield_transactional_session
from forktex.log import setup_logging

setup_logging(service="my-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_engine(settings.db_url, pool_pre_ping=True, pool_recycle=1800)
    yield
    await close_engine()


app = FastAPI(lifespan=lifespan)


@app.get("/projects")
async def list_projects(session: AsyncSession = Depends(yield_transactional_session)):
    ...
```

### Transactions

The outermost caller owns the transaction: whoever opens it commits it once, and rolls it back on
any exception.

```python
@with_transactional_session
async def place_order(session: AsyncSession, *, reference: str) -> Order:
    return await create(session, Order, reference=reference)


await place_order(reference="A-1")                       # opens a session, commits it

async with transactional_session() as session:
    order = await place_order(session, reference="A-2")   # joins this transaction
    await add_line(session, order=order, sku="X")         # the same one
    raise PaymentFailed                                   # both roll back
```

| | |
|:---|:---|
| `transactional_session()` | `async with` — the library commits |
| `yield_transactional_session` | the same unit of work as a generator, for `Depends` |
| `open_session()` | no boundary — you commit |
| `savepoint(session)` | a part allowed to fail without the rest |

Inside the first two, `commit()`, `rollback()` and `begin()` raise `TransactionBoundaryError`.
To abort, raise. Full contract in [docs/database.md](docs/database.md).

`init_engine` / `cache.init` / `storage.init` configure one process-wide default; `Database(url)`,
`Cache(url)` and `StorageClient(config)` build handles directly, so a process can hold several.

## Documentation

One page per module under [`docs/`](docs/): wiring, the public surface, the error contract,
the gotchas. [`docs/development.md`](docs/development.md) is the contributor guide.

## Development

```bash
make install     # poetry install --with dev
make test        # pytest with the coverage floor
make ci          # format-check · lint · license-check · typecheck · audit · test · build · smoke
```

Integration tests use testcontainers, so Docker must be available.

## License

Dual-licensed: AGPL-3.0-or-later, or a commercial license from FORKTEX S.R.L.
(info@forktex.com). See [LICENSE](LICENSE) and [NOTICE](NOTICE).
