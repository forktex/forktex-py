# `forktex.database`

Async PostgreSQL on SQLAlchemy 2: sessions and transactions, ORM bases and mixins, CRUD and
pagination, a filter language for client-supplied queries, advisory locks, a SQL-file migration
runner, constraint-error translation.

PostgreSQL over `asyncpg` (`postgresql+asyncpg://…`).

## Wiring

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:forktex@localhost:5432/postgres
```

```python
# orders.py
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from forktex.api import AppConfig, create_app
from forktex.database import (
    BaseDBModel,
    ScrollResponse,
    TimestampMixin,
    close_engine,
    create,
    get_engine,
    init_engine,
    paginate_scroll,
    transaction,
)
from forktex.types import BaseAppModel


class Order(BaseDBModel, TimestampMixin):
    __tablename__ = "order"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    reference: Mapped[str] = mapped_column(unique=True)


class OrderOut(BaseAppModel):
    id: uuid.UUID
    reference: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_engine(os.environ["DATABASE_URL"], pool_size=10, pool_pre_ping=True)
    async with get_engine().begin() as conn:  # for this example only: use migrations in a real service
        await conn.run_sync(BaseDBModel.metadata.create_all)
    yield
    await close_engine()


app = create_app(AppConfig(title="Orders", lifespan=lifespan))
Session = Depends(transaction.dependency, scope="function")


@app.post("/orders", status_code=201)
async def place_order(reference: str, session: AsyncSession = Session) -> OrderOut:
    order = await create(session, Order, reference=reference)
    return OrderOut(id=order.id, reference=order.reference)


@app.get("/orders")
async def list_orders(cursor: str | None = None, session: AsyncSession = Session) -> ScrollResponse[OrderOut]:
    page = await paginate_scroll(
        session, Order, limit=20, keyset=[Order.created_at, Order.id], cursor=cursor, ascending=False
    )
    return page.apply_to_scroll_data(lambda order: OrderOut(id=order.id, reference=order.reference))
```

```bash
uvicorn orders:app
curl -X POST 'localhost:8000/orders?reference=A-1'
curl localhost:8000/orders
# {"data":[{"id":"…","reference":"A-1"}],"hasMore":false,"nextCursor":null,"total":null,"limit":20}
curl -X POST 'localhost:8000/orders?reference=A-1'
# 409 {"code": "already_exists", "message": "resource already exists", …}
```

- `Depends(transaction.dependency, scope="function")` commits when the route
  returns, before the response is sent. Without `scope="function"` FastAPI sends
  the response first, so a client could be told a write succeeded that then
  fails to commit.

- `init_engine` performs no I/O. Call `verify()` (or wire it into
  `create_app`'s `readiness_probes`) to fail fast on a bad configuration.
- Call `init_engine` in the lifespan, not at import time: at import it binds the
  pool to whichever event loop is current.
- Extra keywords go to SQLAlchemy's `create_async_engine`. Calling `init_engine`
  again disposes the pool it replaces.

## Sessions and transactions

| You need | Use | Who commits |
|:---|:---|:---|
| a unit of work in a route | `Depends(transaction.dependency, scope="function")` | the library, before the response is sent |
| a unit of work anywhere else | `async with transaction() as session:` | the library, when the block exits cleanly |
| a step inside a caller's transaction | pass the session, or `@transaction` | the caller it joined |
| a part that may fail alone | `async with savepoint(session):` | the caller; only this block rolls back |
| many commits, an isolation level, read-only | `async with session() as opened:` | you |

`transaction` is one name in four shapes: a context manager, a decorator, a parameterised
decorator, and `.dependency` for `Depends`. A scope opens one unit of work — entering it twice
raises.

Inside any of them `commit()`, `rollback()` and `begin()` raise `TransactionBoundaryError`. To
abort, raise — the library rolls back and returns the connection.

```python
# transactions.py
import asyncio
import os
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from forktex.database import BaseDBModel, close_engine, get_engine, init_engine, transaction


class Line(BaseDBModel):
    __tablename__ = "line"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    sku: Mapped[str]


@transaction
async def add_line(session: AsyncSession, *, sku: str) -> None:
    session.add(Line(sku=sku))


async def main() -> None:
    await init_engine(os.environ["DATABASE_URL"])
    async with get_engine().begin() as conn:
        await conn.run_sync(BaseDBModel.metadata.create_all)

    await add_line(sku="A1")  # no session given: opens one and commits it

    try:
        async with transaction() as session:
            await add_line(session, sku="B1")  # joins this transaction
            await add_line(session, sku="B2")
            raise RuntimeError("payment failed")  # both lines roll back
    except RuntimeError:
        pass

    async with transaction() as session:
        print(list(await session.scalars(sa.select(Line.sku))))  # ['A1']
    await close_engine()


asyncio.run(main())
```

The decorator binds by parameter name, defaulting to `session`; pass the other arguments by
keyword. `@transaction(param="db")` binds a differently-named one. A decorated function with no
such parameter raises `TypeError` at import.

**Hand the decorator only a session something else commits.** It joins and never commits a session
it was given; a bare `sessionmaker()` then discards the writes at close with no error. A `session()`
block raises instead.

### Letting one part fail

A failed statement aborts the whole PostgreSQL transaction, so every later statement fails with
`current transaction is aborted`. `savepoint()` scopes the damage:

```python
# savepoints.py
import asyncio
import os

import sqlalchemy as sa

from forktex.database import close_engine, init_engine, savepoint, transaction


async def main() -> None:
    await init_engine(os.environ["DATABASE_URL"])
    async with transaction() as session:
        await session.execute(sa.text("CREATE TEMP TABLE item (id int PRIMARY KEY)"))
        for item_id in (1, 2, 2, 3):
            try:
                async with savepoint(session):
                    await session.execute(sa.text("INSERT INTO item VALUES (:id)"), {"id": item_id})
            except sa.exc.IntegrityError:
                print("skipped", item_id)  # only this insert rolled back
        print(list(await session.scalars(sa.text("SELECT id FROM item ORDER BY id"))))  # [1, 2, 3]
    await close_engine()


asyncio.run(main())
```

`@transaction(isolate=True)` takes the savepoint on every caller's behalf. It is a decorator-only
form — `async with transaction(isolate=True)` has no caller's session to nest in and raises.

### Owning the boundary

`session()` has no boundary — for work that is deliberately many transactions, and for fixtures
that seed committed rows. Inside it the session is plain SQLAlchemy, so `.begin()` and
per-transaction execution options work as usual.

Leaving the block with writes the ORM knows about and no commit raises `TransactionBoundaryError`,
and the writes are discarded. Writes issued as raw `text()` SQL are opaque and not tracked.

Don't share one session between concurrent tasks; give each its own.

### More than one pool

`Database(url, **engine_kwargs)` owns its engine and holds no global state. Its
`.transaction()` and `.session()` are the two module functions as methods; `await db.dispose()` on
shutdown. The decorator and `transaction.dependency` only know the module-level default, so a
component owning a `Database` uses `db.transaction()`.

## Public surface

| Name | What it is |
| --- | --- |
| `await init_engine(db_url, *, echo=False, schema_translate_map=None, **engine_kwargs)` | Build the process-wide default engine. Returns `None`. |
| `close_engine()` | Dispose it and clear the handle. |
| `default()` | The process-wide `Database`, or `None` before `init_engine`. |
| `require_default()` | The same, raising `DatabaseNotInitializedError` instead of returning `None`. |
| `verify()` | Async. Opens one connection and discards it. Raises `DatabaseUnreachableError`. |
| `get_engine()` | The default `AsyncEngine` — what `advisory_lock` and DDL take. |
| `Database(url, *, echo=False, schema_translate_map=None, **engine_kwargs)` | An engine and sessionmaker owned explicitly. `.engine`, `.sessionmaker`, `.dispose()`, plus `.transaction()` and `.session()`. |
| `transaction()` | `async with` — one unit of work. |
| `transaction` / `transaction(*, isolate=False, param="session")` | Decorator: joins `param`'s transaction, or opens and commits its own. |
| `transaction.dependency` | The same unit of work as an async generator, for `Depends`. |
| `session()` | A session with no boundary: you commit, or leaving the block raises. |
| `savepoint(session)` | `async with` — an inner transaction. |
| `BaseDBModel` | The declarative base every model inherits. |
| `substrate_base(schema)` | A base on its own `MetaData`, bound to a named schema. |
| `TimestampMixin` | `created_at`, `updated_at`, set by the database. |
| `AuditMixin` | `TimestampMixin` + `created_by_id`, `updated_by_id`, `archived_at`, `is_active`. |
| `NamespacedMixin` | A `namespace` column for tenant scoping, no foreign key. |
| `ReprMixin` | `__repr__` from the primary key. |
| `UtcTimestamp` | The SQLAlchemy column type `TIMESTAMP WITH TIME ZONE` — what `Mapped[datetime]` maps to. Not `forktex.types.UtcDateTime`, which is a Pydantic field annotation. |
| `JsonModelColumn` | A JSONB column typed by a Pydantic model. |
| `create(session, model, **values)` | Insert one row, inside `integrity_boundary()`. |
| `get(session, model, value, *, key="id", options=None)` | One row by key, or `None`. |
| `find_one_by(session, model, **filters)` | One row by equality filters, or `None`. |
| `list_all(session, model, *, options=None)` | Every row. |
| `paginate(session, model, page=1, page_size=100, ...)` | Offset pagination → `PageResponse`. |
| `paginate_scroll(session, model, limit=20, *, keyset, cursor, ascending, ...)` | Keyset pagination → `ScrollResponse`. |
| `Page` | `items`, `hasMore`, `nextCursor`, `total`. |
| `PageResponse` / `ScrollResponse` | `Page` plus `limit`, and `currentPage` / `totalPages` for offset. On the wire their items are `data`, and `PageResponse`'s total is `totalCount`. `apply_to_page_data(fn)` / `apply_to_scroll_data(fn)` map the items, e.g. ORM rows to response models. |
| `encode_cursor(values)` / `decode_cursor(cursor, *, expected_length=None)` | The opaque cursor codec. |
| `keyset_predicate(levels, *, ascending)` | The WHERE clause behind keyset pagination. |
| `crud` | Module: `crud.get`, `crud.create`, `crud.find_one_by`, `crud.paginate`, `crud.paginate_scroll`. |
| `filters` | Module: `filters.FilterOp`, `filters.parse_filter`, `filters.compile_filter`. |
| `identifiers` | Module: `identifiers.validate_identifier`, `validate_schema`, `validate_relation`, `validate_slug`, `is_identifier`. |
| `integrity` | Module: `integrity.integrity_boundary`, `integrity.read_boundary`, the `SQLSTATE_*` constants. |
| `integrity_boundary()` | `async with` — a constraint violation becomes a typed `AppError`. |
| `read_boundary()` | The same for a read-time data exception. |
| `advisory_lock(engine, key)` | Blocking session-scoped Postgres advisory lock. |
| `try_advisory_lock(engine, key)` | Non-blocking; yields whether it was acquired. |
| `xact_lock(session, key)` | Transaction-scoped lock, released at commit. |
| `advisory_key(*parts)` / `key_from_uuid(value)` | Derive a stable 64-bit lock key. |
| `SchemaMigrationRunner(engine, schema, migrations_dir, *, target_schema=None, version_table="schema_version")` | Applies `v0001__name.sql` files under one advisory lock. |
| `ddl` | Module: `ddl.AddColumn`, `ddl.CreateTable`, … for idempotent DDL. |
| `reflect` | Module: `reflect.columns`, `column_types`, `has_table`, `indexes`, `type_ddl`, `udt_names`. |
| `is_identifier(name)` | Whether `name` is a safe SQL identifier. |
| `validate_identifier(name)` / `validate_schema` / `validate_relation` / `validate_slug` | Raise `BadRequestError` unless it is. |
| `TransactionBoundaryError` / `DatabaseNotInitializedError` | See Errors. |

## Models

`AuditMixin` adds a check that `is_active` ⟺ `archived_at IS NULL`. Two options:
`__actor_fk_target__ = "user.id"` adds `ON DELETE SET NULL` foreign keys for the actor columns;
`unique_fields = ["slug"]` creates a unique index over **active rows only**, so an archived row's
slug is reusable. To add your own constraints, concatenate `super().__table_args__` in a
`declared_attr` — assigning `__table_args__` replaces the mixin's.

## CRUD and pagination

Prefer `paginate_scroll` for deep pages. Pass `keyset` — the ordering columns,
most significant first, ending in a unique tiebreaker such as `id` — and hand `next_cursor` back as
`cursor`. Without `order_by`, rows are ordered by the keyset. Cursors are opaque base64; a tampered
one raises `BadRequestError`. For a custom query, build a `Page` with `keyset_predicate`,
`encode_cursor` and `decode_cursor`. All page shapes are camelCase on the wire.

## Filters

```python
# filtering.py
import asyncio
import os
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from forktex.database import BaseDBModel, close_engine, filters, get_engine, init_engine, transaction


class Invoice(BaseDBModel):
    __tablename__ = "invoice"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    status: Mapped[str]
    total: Mapped[int]


async def main() -> None:
    await init_engine(os.environ["DATABASE_URL"])
    async with get_engine().begin() as conn:
        await conn.run_sync(BaseDBModel.metadata.create_all)

    # What a client sends, e.g. as JSON in a query parameter.
    requested = {"and": [{"column": "status", "op": "eq", "value": "open"}, {"column": "total", "op": "gte", "value": 100}]}
    condition = filters.compile_filter(
        filters.parse_filter(requested), filters.ColumnSource(Invoice, allowed={"status", "total"})
    )

    async with transaction() as session:
        session.add_all([Invoice(status="open", total=150), Invoice(status="open", total=20), Invoice(status="paid", total=500)])
        await session.flush()
        print([(i.status, i.total) for i in await session.scalars(sa.select(Invoice).where(condition))])
    await close_engine()


asyncio.run(main())
```

Operators: `eq ne lt lte gt gte in not_in between is_null contains icontains startswith endswith
fuzzy`, combined with `and` / `or` / `not`. `SortKey.parse({"column": …, "direction": "asc"})`
validates sort input the same way.

- **`allowed` is the security boundary.** Without it every mapped column is filterable.
- **`fuzzy` needs `pg_trgm`** on the target database; it fails in Postgres, not in validation.

## Locks

`advisory_lock` yields its connection; commit work done on it inside the block, since anything
uncommitted is rolled back on release.

## Migrations

```sql
-- migrations/v0001__create_events.sql
CREATE TABLE "{schema}".event (id bigserial PRIMARY KEY, name text NOT NULL);
```

```python
# migrate.py
import asyncio
import os
from pathlib import Path

from forktex.database import SchemaMigrationRunner, close_engine, get_engine, init_engine


async def main() -> None:
    await init_engine(os.environ["DATABASE_URL"])
    runner = SchemaMigrationRunner(get_engine(), schema="events", migrations_dir=Path(__file__).parent / "migrations")
    await runner.apply()  # safe to call from every process at startup
    await close_engine()


asyncio.run(main())
```

- Files are `v{NNNN}__{description}.sql`, applied in version order. A misnamed or duplicated
  version raises `BadRequestError` before anything runs.
- `{schema}` in a file is replaced with the target schema by plain substitution, so literal braces
  pass through.
- Each file runs in one transaction with its `schema_version` row, so `CREATE INDEX CONCURRENTLY`
  and `VACUUM` cannot be used.
- A file may hold several statements, over asyncpg's simple-query protocol, which accepts no bind
  parameters. Write literals.
- An applied migration whose content has since changed raises `MigrationError`. A database does
  not re-run one, so an edit never reaches the schema. Write the next migration instead.
- A pending migration numbered below the highest applied version raises `MigrationError`, rather
  than being applied out of order. Renumber it above that version.
- Both checks read the version table's `checksum` column. A version table without that column
  gets it on `apply()`; rows recorded without a checksum are not verified.
- Concurrent callers serialise on an advisory lock; safe to call from every worker on startup.
- `target_schema=` runs the DDL elsewhere; `version_table=` renames the tracking table. Runners
  sharing a target schema need distinct version tables.

## Errors

| Raised | When |
|:---|:---|
| `AlreadyExistsError` | a unique violation in `create` or `integrity_boundary()` |
| `BadRequestError` | any other constraint violation; an unknown column; an invalid cursor, filter, sort or identifier; a stored value invalid for its type inside `read_boundary()` |
| `TransactionBoundaryError` | `commit`/`rollback`/`begin` on a session whose boundary belongs to its opener |
| `DatabaseNotInitializedError` | a module-level function before `init_engine` |
| `DatabaseUnreachableError` | `verify()` could not open a connection |
| `InvalidKeysetError` | a cursor passed without its keyset; `keyset_predicate` with no levels |
| `InvalidAdvisoryKeyError` | `advisory_key()` with no parts; `key_from_uuid()` on a non-UUID |
| `InvalidSchemaChangeError` | `AddColumn` on a column not attached to a `Table` |
| `MigrationError` | a migration script failed; it and its version row rolled back together |

A constraint that fails when `transaction()` commits, such as a deferred one, is translated the same
way. Wrap hand-written writes in `async with integrity_boundary():`, flushing inside it, for the
translation `create` applies. Driver text never reaches the error; the original is the `__cause__`.

## Gotchas

- `forktex.database.UtcTimestamp` is a SQLAlchemy column type; `forktex.types.UtcDateTime` is a
  Pydantic field annotation. Different objects, different places.
- `keyset` **is** the ordering — passing `order_by` with it raises. The last keyset level is the
  tiebreaker and must not be nullable.

- A bare `Mapped[datetime]` is `timestamptz`, and asyncpg refuses to write a naive datetime into it.
- Keyset pagination assumes Postgres's default NULL placement. Don't add `NULLS FIRST`/`NULLS LAST`
  to an ordering you page with a keyset.
- Identifiers are capped at 128 characters but Postgres truncates at 63. Mixed case is safe —
  identifiers are always emitted quoted.
- The index and constraint names the mixins generate are part of a deployed schema; renaming one
  makes Alembic propose a drop and recreate.
