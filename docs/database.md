# `forktex.database`

Async PostgreSQL on SQLAlchemy 2: sessions and transactions, ORM bases and mixins, CRUD and
pagination, a filter language for client-supplied queries, advisory locks, a SQL-file migration
runner, constraint-error translation.

PostgreSQL over `asyncpg` (`postgresql+asyncpg://…`).

## Wiring

`init` performs no I/O: it installs the default and releases whatever it replaced. `verify()` is
the explicit boot probe — call it in your lifespan, or wire it into `create_app`'s
`readiness_probes`, if you want a bad configuration to fail fast rather than on first use.

```python
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from forktex.database import (
    BaseDBModel, TimestampMixin, close_engine, create, init_engine, paginate_scroll,
    yield_transactional_session,
)


class Order(BaseDBModel, TimestampMixin):
    __tablename__ = "order"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    reference: Mapped[str] = mapped_column(unique=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_engine("postgresql+asyncpg://user:pass@localhost/db", pool_size=10, pool_pre_ping=True)
    yield
    await close_engine()


app = FastAPI(lifespan=lifespan)


@app.post("/orders")
async def place_order(reference: str, session: AsyncSession = Depends(yield_transactional_session)):
    return await create(session, Order, reference=reference)


@app.get("/orders")
async def list_orders(cursor: str | None = None, session: AsyncSession = Depends(yield_transactional_session)):
    return await paginate_scroll(
        session, Order, limit=20, keyset=[Order.created_at, Order.id], cursor=cursor, ascending=False
    )
```

Call `init_engine` in the lifespan, not at import time — at import it binds the pool to whichever
event loop is current. Extra keywords go to `create_async_engine`. Re-initialising without
`close_engine()` leaks the previous pool.

## Sessions and transactions

| You need | Use | Who commits |
|:---|:---|:---|
| a unit of work in a route | `Depends(yield_transactional_session)` | the library, when the request succeeds |
| a unit of work anywhere else | `async with transactional_session() as session:` | the library, when the block exits cleanly |
| a step inside a caller's transaction | pass the session, or `@with_transactional_session` | the caller it joined |
| a part that may fail alone | `async with savepoint(session):` | the caller; only this block rolls back |
| many commits, an isolation level, read-only | `async with open_session() as session:` | you |

Inside `transactional_session` and the decorator, `commit()`, `rollback()` and `begin()` raise
`TransactionBoundaryError`. To abort, raise — the library rolls back and returns the connection.

```python
@with_transactional_session
async def add_line(session: AsyncSession, *, order: Order, sku: str) -> None:
    session.add(OrderLine(order=order, sku=sku))


await add_line(order=order, sku="A1")                # no session: opens one, commits it

async with transactional_session() as session:
    session.add(order)
    await add_line(session, order=order, sku="A1")    # joins this transaction
    raise RuntimeError("payment failed")              # order and line both roll back
```

The decorator binds by parameter name, defaulting to `session`; pass the other arguments by
keyword. `@with_transactional_session(param="db")` binds a differently-named one. A decorated
function with no such parameter raises `TypeError` at import.

**Hand the decorator only a session something else commits.** It joins and never commits a session
it was given, so an uncommitted `open_session()` or bare `sessionmaker()` discards the writes at
close, with no error.

### Letting one part fail

A failed statement aborts the whole PostgreSQL transaction, so every later statement fails with
`current transaction is aborted`. `savepoint()` scopes the damage:

```python
for item in batch:
    try:
        async with savepoint(session):
            await upsert(session, item)
    except Exception:
        log.exception("skipped %s", item.id)
```

`@with_transactional_session(isolate=True)` takes the savepoint on every caller's behalf.

### Owning the boundary

`open_session()` has no boundary — for work that is deliberately many transactions, and for
fixtures that seed committed rows. Inside it the session is plain SQLAlchemy, so `session.begin()`
and per-transaction execution options work as usual.

Don't share one session between concurrent tasks; give each its own.

### More than one pool

`Database(url, **engine_kwargs)` owns its engine and holds no global state. Its
`.transactional_session()`, `.yield_transactional_session()` and `.open_session()` are the three
module functions as methods; `await db.dispose()` on shutdown. `with_transactional_session` only
knows the module-level default, so a component owning a `Database` uses `db.transactional_session()`.

## Public surface

| Name | What it is |
| --- | --- |
| `await init_engine(db_url, *, echo=False, schema_translate_map=None, **engine_kwargs)` | Build the process-wide default engine. Returns `None`. |
| `close_engine()` | Dispose it and clear the handle. |
| `default()` | The process-wide `Database`, or `None` before `init_engine`. |
| `require_default()` | The same, raising `DatabaseNotInitializedError` instead of returning `None`. |
| `verify()` | Async. Opens one connection and discards it. Raises `DatabaseUnreachableError`. |
| `get_engine()` | The default `AsyncEngine` — what `advisory_lock` and DDL take. |
| `Database(url, *, echo=False, schema_translate_map=None, **engine_kwargs)` | An engine and sessionmaker owned explicitly. `.engine`, `.sessionmaker`, `.dispose()`, plus the three session methods. |
| `transactional_session()` | `async with` — one unit of work. |
| `yield_transactional_session()` | The same as an async generator, for `Depends`. |
| `open_session()` | A session with no boundary: you commit. |
| `savepoint(session)` | `async with` — an inner transaction. |
| `with_transactional_session(func=None, /, *, isolate=False, param="session")` | Decorator: joins `param`'s transaction, or opens and commits its own. |
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
| `PageResponse` / `ScrollResponse` | `Page` plus `limit`, and `currentPage` / `totalPages` for offset. |
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
from forktex.database import filters

node = filters.parse_filter({"and": [
    {"column": "status", "op": "eq", "value": "open"},
    {"column": "total", "op": "gte", "value": 100},
]})
source = filters.ColumnSource(Order, allowed={"status", "total"})
stmt = select(Order).where(filters.compile_filter(node, source))
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

```python
await SchemaMigrationRunner(engine, schema="my_lib", migrations_dir=Path(__file__).parent / "sql").apply()
```

- Files are `v{NNNN}__{description}.sql`, applied in version order. A misnamed or duplicated
  version raises `BadRequestError` before anything runs.
- `{schema}` in a file is replaced with the target schema by plain substitution, so literal braces
  pass through.
- Each file runs in one transaction with its `schema_version` row, so `CREATE INDEX CONCURRENTLY`
  and `VACUUM` cannot be used.
- A file may hold several statements, over asyncpg's simple-query protocol, which accepts no bind
  parameters. Write literals.
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

Wrap hand-written writes in `async with integrity_boundary():`, flushing inside it, for the
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
