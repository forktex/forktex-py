# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
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

"""Service layer — a thin async wrapper over ``forktex_core.grid``.

Translates the HTTP DTOs (string enums, slugs, relation keys) into core calls
and shapes the responses. Everything is scoped by ``namespace`` (the agent /
tenant state-space). Core raises ``forktex_core.common.errors.*`` which the
app surfaces as the standard error envelope.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from forktex_core.common.errors import NotFoundError
from forktex_core.grid import (
    GridColumn,
    GridIndex,
    GridRelation,
    GridRow,
    GridSection,
    GridTable,
    all_field_types,
    archive_row,
    create_column,
    create_relation,
    create_row,
    create_section,
    create_table,
    effective_capabilities,
    get_active_columns,
    get_field_type,
    get_row,
    get_table,
    list_related,
    patch_row,
    query_rows,
    reconcile_table_indexes,
    relate_rows,
)
from forktex_core.grid.enums import (
    BrowseMode,
    FieldCardinality,
    IndexState,
    Materialization,
    OnDelete,
    Ownership,
    RelationDirection,
    RelationType,
)

from forktex.grid import schemas


# ── Type registry ────────────────────────────────────────────────────────────


def list_type_descriptors() -> list[schemas.TypeDescriptor]:
    """Every registered field type + its built-in capabilities + config schema."""
    out: list[schemas.TypeDescriptor] = []
    for type_id, handler in sorted(all_field_types().items()):
        out.append(
            schemas.TypeDescriptor(
                type_id=type_id,
                capabilities=_caps(handler, None),
                config_schema=handler.config_model.model_json_schema(),
            )
        )
    return out


def _caps(handler, overrides: dict | None) -> schemas.Capabilities:
    caps = effective_capabilities(handler, overrides)
    return schemas.Capabilities(
        filterable=caps.filterable,
        sortable=caps.sortable,
        fuzzy=caps.fuzzy,
        cursor_browsable=caps.cursor_browsable,
        filter_ops=sorted(op.value for op in caps.filter_ops),
        index_kinds=sorted(caps.index_kinds),
        default_index_kind=caps.default_index_kind,
    )


# ── Tables ────────────────────────────────────────────────────────────────────


async def create_table_(
    session: AsyncSession, *, namespace: str, body: schemas.TableCreate
) -> GridTable:
    return await create_table(
        session,
        slug=body.slug,
        label=body.label,
        namespace=namespace,
        ownership=Ownership(body.ownership),
        projection_predicate=body.projection_predicate,
        natural_key=body.natural_key,
        config=body.config,
    )


async def list_tables(session: AsyncSession, *, namespace: str) -> list[GridTable]:
    result = await session.scalars(
        sa.select(GridTable)
        .where(GridTable.namespace == namespace, GridTable.archived_at.is_(None))
        .order_by(GridTable.slug)
    )
    return list(result)


async def describe_table(
    session: AsyncSession, *, namespace: str, slug: str
) -> schemas.TableDescribe:
    table = await get_table(session, slug=slug, namespace=namespace)
    columns = await get_active_columns(session, table_id=table.id)
    sections = await session.scalars(
        sa.select(GridSection).where(
            GridSection.table_id == table.id, GridSection.archived_at.is_(None)
        )
    )
    relations = await session.scalars(
        sa.select(GridRelation).where(
            GridRelation.source_table_id == table.id, GridRelation.archived_at.is_(None)
        )
    )
    indexes = await session.scalars(
        sa.select(GridIndex).where(
            GridIndex.table_id == table.id, GridIndex.archived_at.is_(None)
        )
    )
    return schemas.TableDescribe(
        table=schemas.TableOut.model_validate(table),
        columns=[column_out(c) for c in columns],
        sections=[schemas.SectionOut.model_validate(s) for s in sections],
        relations=[schemas.RelationOut.model_validate(r) for r in relations],
        indexes=[schemas.IndexOut.model_validate(i) for i in indexes],
    )


def column_out(column: GridColumn) -> schemas.ColumnOut:
    handler = get_field_type(column.type_id)
    return schemas.ColumnOut(
        id=column.id,
        key=column.key,
        label=column.label,
        type_id=column.type_id,
        cardinality=column.cardinality,
        materialization=column.materialization,
        is_required=column.is_required,
        is_unique=column.is_unique,
        display_order=column.display_order,
        config=column.config,
        capabilities=_caps(handler, column.capability_overrides),
    )


# ── Columns / sections / relations / indexes ────────────────────────────────────


async def add_column(
    session: AsyncSession, *, namespace: str, slug: str, body: schemas.ColumnCreate
) -> GridColumn:
    table = await get_table(session, slug=slug, namespace=namespace)
    relation_id: uuid.UUID | None = None
    if body.relation_key is not None:
        relation_id = await _relation_id(
            session, table_id=table.id, key=body.relation_key
        )
    return await create_column(
        session,
        table=table,
        key=body.key,
        label=body.label,
        type_id=body.type_id,
        cardinality=FieldCardinality(body.cardinality),
        materialization=Materialization(body.materialization),
        is_required=body.is_required,
        is_unique=body.is_unique,
        config=body.config,
        relation_id=relation_id,
        default_value=body.default_value,
        display_order=body.display_order,
    )


async def add_section(
    session: AsyncSession, *, namespace: str, slug: str, body: schemas.SectionCreate
) -> GridSection:
    table = await get_table(session, slug=slug, namespace=namespace)
    return await create_section(
        session,
        table=table,
        slug=body.slug,
        label=body.label,
        is_default=body.is_default,
        row_filter=body.row_filter,
        sort_spec=body.sort_spec,
        browse_mode=BrowseMode(body.browse_mode),
    )


async def add_relation(
    session: AsyncSession, *, namespace: str, slug: str, body: schemas.RelationCreate
) -> GridRelation:
    source = await get_table(session, slug=slug, namespace=namespace)
    target = await get_table(session, slug=body.target_slug, namespace=namespace)
    through = (
        await get_table(session, slug=body.through_slug, namespace=namespace)
        if body.through_slug
        else None
    )
    return await create_relation(
        session,
        key=body.key,
        source_table=source,
        target_table=target,
        through_table=through,
        relation_type=RelationType(body.relation_type),
        direction=RelationDirection(body.direction),
        on_delete=OnDelete(body.on_delete),
    )


async def add_index(
    session: AsyncSession, *, namespace: str, slug: str, body: schemas.IndexCreate
) -> GridIndex:
    table = await get_table(session, slug=slug, namespace=namespace)
    index = GridIndex(
        table_id=table.id,
        namespace=namespace,
        column_keys=body.column_keys,
        index_kind=body.index_kind,
        is_unique=body.is_unique,
        state=IndexState.pending,
    )
    session.add(index)
    await session.flush()
    return index


async def reconcile(
    session: AsyncSession, *, namespace: str, slug: str, schema: str
) -> list[str]:
    table = await get_table(session, slug=slug, namespace=namespace)
    return await reconcile_table_indexes(session, table=table, schema=schema)


# ── Rows ────────────────────────────────────────────────────────────────────────


async def add_row(
    session: AsyncSession, *, namespace: str, slug: str, body: schemas.RowCreate
) -> GridRow:
    table = await get_table(session, slug=slug, namespace=namespace)
    return await create_row(session, table=table, values=body.values)


async def read_row(session: AsyncSession, *, row_id: uuid.UUID) -> GridRow:
    return await get_row(session, row_id=row_id)


async def update_row(
    session: AsyncSession, *, row_id: uuid.UUID, body: schemas.RowPatch
) -> GridRow:
    row = await get_row(session, row_id=row_id)
    return await patch_row(session, row=row, values=body.values)


async def archive(session: AsyncSession, *, row_id: uuid.UUID) -> None:
    row = await get_row(session, row_id=row_id)
    await archive_row(session, row=row)


async def query(
    session: AsyncSession, *, namespace: str, slug: str, body: schemas.QueryRequest
) -> schemas.QueryResult:
    table = await get_table(session, slug=slug, namespace=namespace)
    result = await query_rows(
        session,
        table=table,
        filter=body.filter,
        sort=body.sort,
        mode=BrowseMode(body.mode),
        limit=body.limit,
        offset=body.offset,
        cursor=body.cursor,
        include_total=body.include_total,
    )
    return schemas.QueryResult(
        rows=[schemas.RowOut(id=r.id, payload=r.payload) for r in result.rows],
        next_cursor=result.next_cursor,
        total=result.total,
    )


async def relate(
    session: AsyncSession,
    *,
    namespace: str,
    slug: str,
    row_id: uuid.UUID,
    body: schemas.RelateRequest,
):
    table = await get_table(session, slug=slug, namespace=namespace)
    relation = await _relation(session, table_id=table.id, key=body.relation_key)
    source_row = await get_row(session, row_id=row_id)
    target_row = await get_row(session, row_id=body.target_row_id)
    await relate_rows(
        session,
        relation=relation,
        source_row=source_row,
        target_row=target_row,
        payload=body.payload,
    )


async def list_links(
    session: AsyncSession,
    *,
    namespace: str,
    slug: str,
    row_id: uuid.UUID,
    relation_key: str,
):
    table = await get_table(session, slug=slug, namespace=namespace)
    relation = await _relation(session, table_id=table.id, key=relation_key)
    source_row = await get_row(session, row_id=row_id)
    return await list_related(session, relation=relation, source_row=source_row)


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _relation(
    session: AsyncSession, *, table_id: uuid.UUID, key: str
) -> GridRelation:
    relation = await session.scalar(
        sa.select(GridRelation).where(
            GridRelation.source_table_id == table_id,
            GridRelation.key == key,
            GridRelation.archived_at.is_(None),
        )
    )
    if relation is None:
        raise NotFoundError(
            f"Relation '{key}' not found", details={"relation_key": key}
        )
    return relation


async def _relation_id(
    session: AsyncSession, *, table_id: uuid.UUID, key: str
) -> uuid.UUID:
    return (await _relation(session, table_id=table_id, key=key)).id
