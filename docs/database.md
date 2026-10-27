# `forktex.database`

Async PostgreSQL on SQLAlchemy 2: engine and session lifecycle, ORM bases and mixins, CRUD and
pagination helpers, a filter language for client-supplied queries, advisory locks, a SQL-file
migration runner, and constraint-error translation.

## Install

- Python 3.14+
- PostgreSQL, through the `asyncpg` driver (`postgresql+asyncpg://…` URLs)
- SQLAlchemy 2.0 — sessions are plain `AsyncSession`s

Always bundled, no extra required:

```bash
pip install forktex
```

## Wiring

```python
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from forktex.database import (
    BaseDBModel, TimestampMixin, close_engine, create, init_engine, paginate_scroll, session_scope,
)


class Order(BaseDBModel, TimestampMixin):
    __tablename__ = "order"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    reference: Mapped[str] = mapped_column(unique=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine("postgresql+asyncpg://user:pass@localhost/db", pool_size=10, pool_pre_ping=True)
    yield
    await close_engine()


app = FastAPI(lifespan=lifespan)


@app.post("/orders")
async def place_order(reference: str, session: AsyncSession = Depends(session_scope)):
    return await create(session, Order, reference=reference)   # committed when the request succeeds


@app.get("/orders")
async def list_orders(cursor: str | None = None, session: AsyncSession = Depends(session_scope)):
    return await paginate_scroll(
        session, Order, limit=20, keyset=[Order.created_at, Order.id], cursor=cursor, ascending=False
    )
```

Call `init_engine` once, in the lifespan — not at import time, which binds the pool to whichever
event loop is current. Extra keywords go to `create_async_engine`. Re-initialising without
`close_engine()` first logs a warning and leaks the previous pool.

## Public surface

`__all__`:

| Name | What it is |
| --- | --- |
| `init_engine(db_url, *, echo=False, schema_translate_map=None, **engine_kwargs)` | Build the process-wide default engine; returns its sessionmaker. Extra kwargs go to `create_async_engine`. |
| `close_engine()` | Dispose the default engine and clear the handle. |
| `Database(url, *, echo=False, schema_translate_map=None, **engine_kwargs)` | An engine + sessionmaker owned explicitly, holding no global state. `.engine`, `.sessionmaker`, `.session()`, `.unmanaged_session()`, `.session_scope()`, `.dispose()`. |
| `get_session()` | `async with` — one unit of work, committed on success, rolled back on raise. |
| `session_scope()` | The same as a plain generator, for `Depends`. |
| `unmanaged_session()` | A session with no transaction boundary: you commit. |
| `savepoint(session)` | `async with` — an inner transaction, so a caught failure discards only this block. |
| `with_transactional_session(func=None, /, *, isolate=False, param="session")` | Decorator: joins `param`'s transaction, or opens and commits its own. |
| `TransactionBoundaryError` | `commit`/`rollback`/`begin` on a session whose boundary belongs to its opener. |
| `DatabaseNotInitializedError` | A session was requested before `init_engine`. |
| `BaseDBModel` | The declarative base every model inherits. Carries the `type_annotation_map` and `ReprMixin`. |
| `substrate_base(schema)` | A declarative base bound to a named Postgres schema. |
| `TimestampMixin` | `created_at` / `updated_at`, timezone-aware. |
| `AuditMixin` | Soft delete (`archived_at`) plus the timestamps. |
| `NamespacedMixin` | Tenant isolation column and its index. |
| `ReprMixin` | A `__repr__` built from the primary key. |
| `UtcDateTime` | `TIMESTAMP(timezone=True)` — what `Mapped[datetime]` maps to. |
| `JsonModelColumn` | A JSONB column typed by a Pydantic model. |
| `create(session, model, **values)` | Insert one row, inside `integrity_boundary()`. |
| `get(session, model, value, *, key="id", options=None)` | One row by key, or `None`. |
| `find_one_by(session, model, **filters)` | One row by equality filters, or `None`. |
| `list_all(session, model, *, options=None)` | Every row. |
| `paginate(session, model, page=1, page_size=100, ...)` | Offset pagination → `PageResponse`. |
| `paginate_scroll(session, model, limit=20, ...)` | Keyset pagination → `ScrollResponse`. |
| `Page` | The one page shape: `items`, `hasMore`, `nextCursor`, optional `total`. |
| `PageResponse` / `ScrollResponse` | `Page` plus offset metadata (`limit`, `currentPage`). |
| `encode_cursor(values)` / `decode_cursor(cursor, *, expected_length=None)` | The opaque cursor codec. Never parse a cursor by hand. |
| `keyset_predicate(levels, *, ascending)` | The WHERE clause behind keyset pagination. |
| `filters` | Module: a filter language for client-supplied queries. `filters.FilterOp`, `filters.apply`. |
| `integrity_boundary()` | `async with` — maps a constraint violation to a typed `AppError` by SQLSTATE. |
| `read_boundary()` | The same for a read-time data exception. |
| `advisory_lock(engine, key)` | Blocking session-scoped Postgres advisory lock. |
| `try_advisory_lock(engine, key)` | Non-blocking; yields whether it was acquired. |
| `xact_lock(session, key)` | Transaction-scoped lock on the caller's session. |
| `advisory_key(*parts)` | Derive a stable 64-bit lock key. Never `hashtext()`. |
| `key_from_uuid(value)` | A lock key from a UUID. |
| `SchemaMigrationRunner(engine, schema, migrations_dir, *, target_schema=None, version_table="schema_version")` | Applies `v0001__description.sql` files under one advisory lock. |
| `ddl` | Module: `ddl.AddColumn`, `ddl.CreateTable`, … for idempotent DDL. |
| `reflect` | Module: `reflect.columns(session, table, schema=...)` and friends. |
| `is_identifier(name)` | Whether `name` is a safe SQL identifier. |
| `validate_identifier(name, what="identifier")` | Raise `BadRequestError` unless it is. |
| `validate_schema(schema)` / `validate_relation(relation)` / `validate_slug(slug)` | The same for a schema, a relation and a slug. |

## Sessions and transactions

Four rules:

1. **One unit of work per entry point.** The outermost caller opens the transaction; the library
   commits it once, on success, and rolls it back on any exception.
2. **Nesting joins — it does not nest.** A function handed a session participates in that
   transaction and gets no boundary of its own, so it cannot half-apply.
3. **The boundary belongs to whoever opened it.** On a session from `get_session`,
   `session_scope`, `Database.session()` or the decorator, `commit()`, `rollback()` and `begin()`
   raise `TransactionBoundaryError`. To abort, raise.
4. **Divisible work is asked for by name** — `savepoint()` or `unmanaged_session()`.

| You need | Use | Who commits |
|:---|:---|:---|
| A unit of work in a route | `session: AsyncSession = Depends(session_scope)` | The dependency, when the request succeeds |
| A unit of work in a worker or script | `async with get_session() as session:` | The block, when it exits cleanly |
| A step inside a caller's transaction | pass the session, or `@with_transactional_session` | The caller — the step joins its transaction |
| A part that may fail without taking the rest | `async with savepoint(session):` | The caller; only this block rolls back |
| Several commits, an isolation level, read-only | `async with unmanaged_session() as session:` | You |

On a raise, the owned session rolls back and its connection returns to the pool immediately.

> Use `Depends(session_scope)`, not `Depends(get_session)`: `get_session` returns a context manager,
> which FastAPI would inject as-is instead of a session.

### Why `commit()` is refused

A mid-way commit is not a harmless no-op. It makes everything before it durable, so a later failure
leaves the unit of work half-applied:

```python
async with get_session() as session:
    session.add(parent)
    await session.commit()        # TransactionBoundaryError
    session.add(child)
    raise RuntimeError("boom")    # without the guard: parent is in the database, child is not
```

Django refuses `commit`, `rollback` and autocommit changes inside `atomic()` for the same reason,
and SQLAlchemy itself raises `InvalidRequestError` on a second `session.begin()`. To abort, raise:
the exception is the signal, and the library rolls back.

### `with_transactional_session`

```python
@with_transactional_session
async def add_line(session: AsyncSession, *, order: Order, sku: str) -> None:
    session.add(OrderLine(order=order, sku=sku))


await add_line(order=order, sku="A1")            # no session: opens one, commits it

async with get_session() as session:
    session.add(order)
    await add_line(session, order=order, sku="A1")   # joins this transaction
    raise RuntimeError("payment failed")             # order and line both roll back
```

- **Given a session** — positionally or as `session=`, so methods work — the function joins that
  transaction. Its work lands or rolls back with its caller's.
- **Given none**, it opens one and commits on success. Do this at entry points only: a decorated
  call that omits the session *inside* a transaction runs in a separate one, which cannot see the
  outer transaction's uncommitted rows.

> **Hand it only a session something will commit.** Joining means the decorator never commits a
> session it was given. Pass one from `unmanaged_session()` or a bare `sessionmaker()` and forget
> to commit, and the writes are discarded at close with no error. `get_session()` and
> `session_scope()` commit; you commit an `unmanaged_session()`.

The session is bound **by parameter name**, defaulting to `session`. Nothing is shuffled out of the
way for a positional call, so pass the other arguments by keyword. A decorated function with no
such parameter is a `TypeError` at import.

```python
@with_transactional_session(param="db")          # bind a differently-named parameter
async def add_line(db: AsyncSession, *, sku: str) -> None: ...
```

### Letting one part fail

Without a savepoint, a failed statement marks the whole PostgreSQL transaction aborted and every
later statement fails with `current transaction is aborted`. `savepoint()` is how a batch survives
one bad row:

```python
for item in batch:
    try:
        async with savepoint(session):
            await upsert(session, item)
    except Exception:
        log.exception("skipped %s", item.id)
```

The caller decides this, because only the caller knows whether a part may fail independently. When
a function should always be isolated, `@with_transactional_session(isolate=True)` takes the
savepoint on its callers' behalf.

### Owning the boundary yourself

`unmanaged_session()` has no boundary — for work that is deliberately many transactions, and for
test fixtures that seed committed rows:

```python
async with unmanaged_session() as session:
    for chunk in chunks:
        await write(session, chunk)
        await session.commit()
```

Inside it the session is plain SQLAlchemy, so `session.begin()` and per-transaction options work as
usual:

```python
async with unmanaged_session() as session:
    await session.connection(execution_options={"isolation_level": "SERIALIZABLE"})
    ...
    await session.commit()
```

Don't share one session between concurrent tasks (`asyncio.gather`); give each its own.

### More than one pool

`Database(url, schema_translate_map=..., **engine_kwargs)` owns its own engine and holds no global
state. `db.session()`, `db.unmanaged_session()`, `db.session_scope()` and `db.sessionmaker` behave
like the module-level functions; call `await db.dispose()` on shutdown.

`with_transactional_session` is sugar over the module-level default, so a component that owns its
own `Database` uses `db.session()` directly rather than the decorator.

## Models

| Name | Purpose |
|:---|:---|
| `BaseDBModel` | Declarative base. `StrEnum` → non-native string column; `datetime` → `timestamptz` |
| `substrate_base(schema)` | A base on its **own** `MetaData`, for a library-owned schema kept out of your `create_all` |
| `UtcDateTime` | The timezone-aware column type (`TIMESTAMP WITH TIME ZONE`) |
| `TimestampMixin` | `created_at`, `updated_at` — set by the database |
| `AuditMixin` | `TimestampMixin` + `created_by_id`, `updated_by_id`, `archived_at`, `is_active`, and a check that `is_active` ⟺ `archived_at IS NULL` |
| `NamespacedMixin` | A `namespace` string column for tenant scoping, with no foreign key |
| `ReprMixin` | Readable `__repr__` |
| `JsonModelColumn` | Serialise lists of Pydantic models into a JSON column |

`AuditMixin` options: `__actor_fk_target__ = "user.id"` adds `ON DELETE SET NULL` foreign keys for
the actor columns; `unique_fields = ["slug"]` creates a unique index over **active** rows only, so an
archived row's slug can be reused. To add constraints of your own, concatenate
`super().__table_args__` in a `declared_attr` — assigning `__table_args__` replaces the mixin's.

## CRUD and pagination

| Function | Returns |
|:---|:---|
| `get(session, Model, value, *, key="id", options=None)` | The row or `None` |
| `find_one_by(session, Model, **filters)` | The row or `None` |
| `list_all(session, Model, *, options=None)` | Every row |
| `create(session, Model, **values)` | The flushed row; constraint violations translated (see Errors) |
| `paginate(session, Model, page=1, page_size=100, conditions, order_by, joins, options)` | `PageResponse` — offset paging, always counts |
| `paginate_scroll(session, Model, limit=20, conditions, order_by, joins, options, *, keyset, cursor, ascending)` | `ScrollResponse` — keyset paging, never counts |

Prefer `paginate_scroll`: its cost does not grow with depth. Pass `keyset` — the ordering columns,
most significant first, ending in a unique tiebreaker such as `id` — and hand back `next_cursor` as
`cursor` for the following page. Without `order_by`, rows are ordered by the keyset. A cursor is
opaque base64; a tampered one raises `BadRequestError`.

Page shapes (all camelCase on the wire):

| Type | Wire fields |
|:---|:---|
| `Page` | `items`, `hasMore`, `nextCursor`, `total` |
| `ScrollResponse` | `data`, `hasMore`, `nextCursor`, `total`, `limit` |
| `PageResponse` | `data`, `hasMore`, `nextCursor`, `totalCount`, `limit`, `currentPage`, `totalPages` |

For a custom query, build a `Page` yourself with `keyset_predicate`, `encode_cursor` and
`decode_cursor`.

## Filters

`forktex.database.filters` turns a client-supplied JSON filter into a SQL expression:

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
fuzzy`, combined with `and` / `or` / `not`. Malformed input, unknown operators, names that are not
mapped columns, and over-deep or over-long filters raise `BadRequestError`.

**`allowed` is the security boundary.** Without it every mapped column — including internal ones —
is filterable. `SortKey.parse({"column": ..., "direction": "asc"|"desc"})` validates sort input the
same way.

**`fuzzy` needs `pg_trgm`.** It compiles to the `%` similarity operator, so the extension has to be
installed on the target database (`CREATE EXTENSION IF NOT EXISTS pg_trgm`). Without it the query
fails in Postgres, not in validation. Every other operator is plain SQL.

## Locks

| Name | Scope | Use |
|:---|:---|:---|
| `advisory_lock(engine, key)` | Its own connection | Block until held — e.g. one migrator at a time |
| `try_advisory_lock(engine, key)` | Its own connection | Yields `True`/`False` — e.g. leader election |
| `xact_lock(session, key)` | The caller's transaction | Serialise work inside a transaction; released at commit |

Derive keys with `advisory_key(*parts)` (or `key_from_uuid(id)` for a row id). `advisory_lock`
yields its connection; commit work done on it inside the block, since anything left uncommitted is
rolled back on release.

## Migrations

`SchemaMigrationRunner` applies plain SQL files to a schema your own migrations do not manage:

```python
await SchemaMigrationRunner(engine, schema="my_lib", migrations_dir=Path(__file__).parent / "sql").apply()
```

- Files are named `v{NNNN}__{description}.sql` and applied in version order. A misnamed `v*.sql`
  file or a duplicated version raises `BadRequestError` before anything runs.
- `{schema}` inside a file is replaced with the target schema. The substitution is a plain
  replacement, not `str.format`, so literal braces — a JSONB default, a PL/pgSQL block — pass
  through untouched.
- Each file runs in one transaction together with its row in `{schema}.schema_version`, so a
  failure leaves neither behind. That means a statement Postgres forbids inside a transaction
  block — `CREATE INDEX CONCURRENTLY`, `VACUUM` — cannot be used in a migration file.
- A file may hold several statements: it is sent over asyncpg's simple-query protocol, which in
  exchange accepts no bind parameters. Write literals.
- Concurrent callers serialise on an advisory lock; safe to call from every worker on startup.
- `target_schema=` runs the DDL in another schema; `version_table=` renames the tracking table.
  Runners that share a target schema need distinct version tables.

## Errors

| Raised | When |
|:---|:---|
| `AlreadyExistsError` | A unique violation in `create` or `integrity_boundary()` |
| `BadRequestError` | Any other constraint violation; an invalid cursor; a malformed filter or sort; a stored value invalid for its type inside `read_boundary()`; an invalid identifier |
| `DatabaseNotInitializedError` | A module-level function before `init_engine` (an `AppError` and a `RuntimeError`) |
| `ValueError` | A programming error: a cursor passed without its keyset |

Wrap hand-written writes in `async with integrity_boundary():` (flush inside it) to get the same
translation `create` applies. Driver messages never reach the error; the original is chained as
`__cause__`.

## Other modules

- `ddl` — `AddColumn`/`DropColumn` plus Core's `CreateTable`, `CreateIndex`, `CreateSchema` and their
  `Drop*` counterparts, all quoted by the dialect.
- `reflect` — `columns`, `column_types`, `has_table`, `indexes`, `type_ddl`, `udt_names` over
  SQLAlchemy's inspector; each accepts a session or a connection.
- `validate_identifier`, `validate_schema`, `validate_slug`, `validate_relation`, `is_identifier`.

## Gotchas

- A bare `Mapped[datetime]` is `timestamptz`. asyncpg refuses to write an aware datetime into a
  naive column, so a naive one is a latent crash.
- `BaseDBModel` sets `eager_defaults` so `updated_at` is fetched with `RETURNING`; reading it after
  an update would otherwise raise `MissingGreenlet`. It is merged into a model's own
  `__mapper_args__`.
- Keyset pagination assumes Postgres's default NULL placement — last ascending, first descending.
  Don't add `NULLS FIRST`/`NULLS LAST` to an ordering you page with a keyset.
- Identifiers are capped at 128 characters, but Postgres truncates at 63: keep names shorter.
  Mixed case is accepted because the library always emits identifiers quoted.
- The index and constraint names the mixins generate are part of the schema a deployed database
  already holds. Renaming one makes Alembic autogenerate propose dropping and recreating it.
