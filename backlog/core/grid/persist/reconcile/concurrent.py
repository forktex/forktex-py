# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of forktex-core.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Out-of-band ``CONCURRENTLY`` physical reconcile — the default under
``ReconcileOptions.concurrently=True``.

Postgres forbids ``CREATE/DROP INDEX CONCURRENTLY`` inside a transaction block, so this
runs the physical phase (index builds, the promoted-column sidecar's unique index,
its backfill) on a dedicated connection in AUTOCOMMIT isolation, one statement at a
time. A build failure marks that one structure ``invalid`` in the returned outcomes
and this function keeps going — one broken index must not block reconciling the
rest of the table, or the other tables in the same ``apply()`` call.

Deliberately does not reuse the ORM-mapped ``GridRow``/``GridColumn``/``GridIndex``
classes for anything executed on the AUTOCOMMIT connection: those resolve through
``schema_translate_map``, which this connection is not guaranteed to carry (see
``indexes._grid_row_for``'s docstring — the same reasoning applies here). Every
statement below names its schema explicitly instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from forktex_core.database import ddl, reflect
from forktex_core.database.models import UtcDateTime
from forktex_core.grid.domain.enums import IndexState, Materialization
from forktex_core.grid.identifiers import is_identifier
from forktex_core.grid.persist import GridColumn, GridIndex, GridTable
from forktex_core.grid.persist.reconcile.indexes import (
    _casts_token,
    _column_casts,
    build_drop_index,
    build_payload_index,
    get_index_kind,
    index_name,
)
from forktex_core.grid.persist.reconcile.sidecar import (
    _promoted_columns,
    _sidecar_table,
    _sql_type,
    sidecar_index_name,
    sidecar_table_name,
)
from forktex_core.log import get_logger

logger = get_logger(__name__)


class PhysicalOutcome(BaseModel):
    """One index/sidecar build's result under the ``concurrently=True`` path."""

    model_config = ConfigDict(frozen=True)

    table: str
    index_name: str | None = None
    kind: str  # "index" | "promoted_unique_index" | "promoted_backfill"
    state: str  # IndexState.live / IndexState.invalid, as a plain string
    error: str | None = None


def _grid_row_raw(schema: str) -> sa.Table:
    """A minimal, explicit-schema ``grid_row`` for the backfill's source side.

    Deliberately not the ORM-mapped ``GridRow`` — see the module docstring.
    """
    return sa.Table(
        "grid_row",
        sa.MetaData(),
        sa.Column("id", sa.UUID(as_uuid=True)),
        sa.Column("table_id", sa.UUID(as_uuid=True)),
        sa.Column("payload", JSONB),
        sa.Column("archived_at", UtcDateTime),
        schema=schema,
    )


async def _run(
    conn: AsyncConnection,
    outcomes: list[PhysicalOutcome],
    *,
    table_slug: str,
    name: str | None,
    kind: str,
    statement: object,
) -> bool:
    """Execute one statement on ``conn``; record its outcome; never raise.

    One failing structure must not abort the rest of this table's (or this
    ``apply()`` call's other tables') reconcile — that is the entire point of
    running these out-of-band rather than in the enclosing transaction.
    """
    try:
        await conn.execute(statement)  # type: ignore[arg-type]
    except Exception as exc:
        logger.warning(
            "grid: concurrent %s failed for table %r (index %r)",
            kind,
            table_slug,
            name,
            exc_info=True,
        )
        outcomes.append(
            PhysicalOutcome(table=table_slug, index_name=name, kind=kind, state=IndexState.invalid, error=str(exc))
        )
        return False
    outcomes.append(PhysicalOutcome(table=table_slug, index_name=name, kind=kind, state=IndexState.live))
    return True


async def reconcile_table_indexes_concurrently(
    conn: AsyncConnection,
    session: AsyncSession,
    *,
    table: GridTable,
    schema: str,
) -> list[PhysicalOutcome]:
    """``CONCURRENTLY`` equivalent of :func:`indexes.reconcile_table_indexes`.

    Reads the same declared state as the transactional reconciler via ``session``
    (plain ``SELECT``s, safe regardless of transaction state); runs each
    ``CREATE``/``DROP INDEX CONCURRENTLY`` on ``conn`` (must already be in
    AUTOCOMMIT isolation); marks each ``GridIndex``'s ``state``/``physical_name``
    via ``session`` once every statement has run.
    """
    outcomes: list[PhysicalOutcome] = []

    columns_by_key = {
        c.key: c
        for c in await session.scalars(
            sa.select(GridColumn).where(GridColumn.table_id == table.id, GridColumn.archived_at.is_(None))
        )
    }
    all_columns = list(await session.scalars(sa.select(GridColumn).where(GridColumn.table_id == table.id)))
    declared = list(
        await session.scalars(
            sa.select(GridIndex).where(GridIndex.table_id == table.id, GridIndex.archived_at.is_(None))
        )
    )

    # Declared indexes: rename (drop old physical name) then create/ensure current.
    for gi in declared:
        spec = get_index_kind(gi.index_kind)
        casts = _column_casts(list(gi.column_keys), columns_by_key, using=spec.using)
        name = index_name(
            "gux" if gi.is_unique else "gix",
            gi.namespace,
            gi.table_id,
            ",".join(gi.column_keys),
            gi.index_kind,
            gi.is_unique,
            _casts_token(casts),
        )
        if gi.physical_name and gi.physical_name != name:
            drop = build_drop_index(name=gi.physical_name, schema=schema, concurrently=True)
            await _run(conn, outcomes, table_slug=table.slug, name=gi.physical_name, kind="index", statement=drop)
        create = ddl.CreateIndex(
            build_payload_index(
                name=name,
                schema=schema,
                table_id=gi.table_id,
                columns=casts,
                using=spec.using,
                opclass=spec.opclass,
                unique=gi.is_unique,
                concurrently=True,
            ),
            if_not_exists=True,
        )
        ok = await _run(conn, outcomes, table_slug=table.slug, name=name, kind="index", statement=create)
        gi.physical_name = name
        gi.state = IndexState.live if ok else IndexState.invalid

    # Implicit per-column unique indexes: drop every column's implicit index first
    # (IF EXISTS — a no-op where none exists), then recreate only for columns still
    # active + unique + payload. Two full passes, matching the transactional
    # reconciler's ordering, since a create and its own prior drop share a name.
    implicit_names = {
        column.id: index_name("gux", column.namespace, column.table_id, column.key, "btree", True)
        for column in all_columns
    }
    for column in all_columns:
        drop = build_drop_index(name=implicit_names[column.id], schema=schema, concurrently=True)
        await _run(conn, outcomes, table_slug=table.slug, name=implicit_names[column.id], kind="index", statement=drop)
    for column in all_columns:
        if column.archived_at is None and column.is_unique and column.materialization == Materialization.payload:
            name = implicit_names[column.id]
            create = ddl.CreateIndex(
                build_payload_index(
                    name=name,
                    schema=schema,
                    table_id=column.table_id,
                    columns=_column_casts([column.key], columns_by_key, using="btree"),
                    using="btree",
                    opclass=None,
                    unique=True,
                    concurrently=True,
                ),
                if_not_exists=True,
            )
            await _run(conn, outcomes, table_slug=table.slug, name=name, kind="index", statement=create)

    # Archived declarations: drop the physical index.
    archived = await session.scalars(
        sa.select(GridIndex).where(
            GridIndex.table_id == table.id,
            GridIndex.archived_at.is_not(None),
            GridIndex.physical_name.is_not(None),
        )
    )
    for gi in archived:
        if gi.physical_name is None:  # (the query already filters these out)
            continue
        drop = build_drop_index(name=gi.physical_name, schema=schema, concurrently=True)
        ok = await _run(conn, outcomes, table_slug=table.slug, name=gi.physical_name, kind="index", statement=drop)
        if ok:
            gi.physical_name = None
            gi.state = IndexState.pending

    await session.commit()
    return outcomes


async def reconcile_table_promoted_concurrently(
    conn: AsyncConnection,
    session: AsyncSession,
    *,
    table: GridTable,
    schema: str,
) -> list[PhysicalOutcome]:
    """``CONCURRENTLY`` equivalent of :func:`sidecar.reconcile_table_promoted`.

    ``CREATE TABLE``/``ADD COLUMN``/``DROP COLUMN`` are cheap metadata-only
    operations (no volatile default, so no table rewrite) and run directly on
    ``conn`` without needing ``CONCURRENTLY``. The sidecar's own unique index and
    the backfill are the expensive parts: the index is built ``CONCURRENTLY``,
    and the backfill runs as its own statement on the AUTOCOMMIT connection rather
    than nested inside the rest of this ``apply()`` call's transaction — it no
    longer extends that transaction's lock-hold time. Chunking the backfill itself
    (for very large tables) is tracked as follow-up debt, not implemented here.
    """
    outcomes: list[PhysicalOutcome] = []
    all_columns = list(await session.scalars(sa.select(GridColumn).where(GridColumn.table_id == table.id)))
    promoted = _promoted_columns([c for c in all_columns if c.archived_at is None])
    name = sidecar_table_name(table.id)
    sidecar = _sidecar_table(schema, name, promoted)
    exists = await reflect.has_table(session, name, schema=schema)

    if not promoted:
        if exists:
            await conn.execute(ddl.DropTable(sidecar, if_exists=True))
        return outcomes

    await conn.execute(ddl.CreateTable(_sidecar_table(schema, name, ()), if_not_exists=True))

    desired = {c.promoted_column for c in promoted}
    present = await reflect.columns(session, name, schema=schema) - {"row_id"}
    for stale in present - desired:
        if is_identifier(stale):
            await conn.execute(ddl.DropColumn(name, stale, schema=schema, if_exists=True))

    for col in promoted:
        native = col.promoted_column
        if native is None:  # (filtered above; narrows for the type checker)
            continue
        column = sidecar.c[native]
        if native not in present:
            await conn.execute(ddl.AddColumn(column, if_not_exists=True))
        idx = sidecar_index_name(name, native, unique=True)
        if col.is_unique:
            create = ddl.CreateIndex(
                sa.Index(idx, column, unique=True, postgresql_concurrently=True), if_not_exists=True
            )
            await _run(conn, outcomes, table_slug=table.slug, name=idx, kind="promoted_unique_index", statement=create)
        else:  # flipped off - the sidecar must stop enforcing uniqueness
            drop = ddl.DropIndex(sa.Index(idx, column, postgresql_concurrently=True), if_exists=True)
            await _run(conn, outcomes, table_slug=table.slug, name=idx, kind="promoted_unique_index", statement=drop)

    raw_row = _grid_row_raw(schema)
    selected = [raw_row.c.id] + [
        raw_row.c.payload[c.key].astext.cast(_sql_type(c)) for c in promoted if c.promoted_column
    ]
    source = sa.select(*selected).where(raw_row.c.table_id == table.id, raw_row.c.archived_at.is_(None))
    targets = ["row_id"] + [c.promoted_column for c in promoted if c.promoted_column]
    backfill = pg_insert(sidecar).from_select(targets, source)
    backfill = backfill.on_conflict_do_update(
        index_elements=[sidecar.c.row_id], set_={n: backfill.excluded[n] for n in targets if n != "row_id"}
    )
    await _run(conn, outcomes, table_slug=table.slug, name=name, kind="promoted_backfill", statement=backfill)

    return outcomes


__all__ = [
    "PhysicalOutcome",
    "reconcile_table_indexes_concurrently",
    "reconcile_table_promoted_concurrently",
]
