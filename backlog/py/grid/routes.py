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

"""The grid HTTP router — self-describing dynamic config + CRUD + query.

Namespace (the agent/tenant state-space scope) is taken from the
``X-Grid-Namespace`` header (default ``""`` = root). All operations delegate to
:mod:`forktex.grid.service`; core raises map to the standard error envelope.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forktex.grid import schemas, service

router = APIRouter(prefix="/grid", tags=["grid"])


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Per-request session that commits on success, rolls back on error."""
    sessionmaker = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_namespace(x_grid_namespace: str = Header(default="")) -> str:
    return x_grid_namespace


# ── Self-description ─────────────────────────────────────────────────────────


@router.get("/types", response_model=list[schemas.TypeDescriptor])
def list_types() -> list[schemas.TypeDescriptor]:
    return service.list_type_descriptors()


# ── Tables ────────────────────────────────────────────────────────────────────


@router.post("/tables", response_model=schemas.TableOut, status_code=201)
async def create_table(
    body: schemas.TableCreate,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> schemas.TableOut:
    table = await service.create_table_(db, namespace=namespace, body=body)
    return schemas.TableOut.model_validate(table)


@router.get("/tables", response_model=list[schemas.TableOut])
async def list_tables(
    db: AsyncSession = Depends(get_db), namespace: str = Depends(get_namespace)
) -> list[schemas.TableOut]:
    tables = await service.list_tables(db, namespace=namespace)
    return [schemas.TableOut.model_validate(t) for t in tables]


@router.get("/tables/{slug}", response_model=schemas.TableDescribe)
async def describe_table(
    slug: str,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> schemas.TableDescribe:
    return await service.describe_table(db, namespace=namespace, slug=slug)


# ── Schema configuration ────────────────────────────────────────────────────


@router.post(
    "/tables/{slug}/columns", response_model=schemas.ColumnOut, status_code=201
)
async def add_column(
    slug: str,
    body: schemas.ColumnCreate,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> schemas.ColumnOut:
    column = await service.add_column(db, namespace=namespace, slug=slug, body=body)
    return service.column_out(column)


@router.post(
    "/tables/{slug}/sections", response_model=schemas.SectionOut, status_code=201
)
async def add_section(
    slug: str,
    body: schemas.SectionCreate,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> schemas.SectionOut:
    section = await service.add_section(db, namespace=namespace, slug=slug, body=body)
    return schemas.SectionOut.model_validate(section)


@router.post(
    "/tables/{slug}/relations", response_model=schemas.RelationOut, status_code=201
)
async def add_relation(
    slug: str,
    body: schemas.RelationCreate,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> schemas.RelationOut:
    relation = await service.add_relation(db, namespace=namespace, slug=slug, body=body)
    return schemas.RelationOut.model_validate(relation)


@router.post("/tables/{slug}/indexes", response_model=schemas.IndexOut, status_code=201)
async def add_index(
    slug: str,
    body: schemas.IndexCreate,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> schemas.IndexOut:
    index = await service.add_index(db, namespace=namespace, slug=slug, body=body)
    return schemas.IndexOut.model_validate(index)


@router.post("/tables/{slug}/reconcile", response_model=list[str])
async def reconcile(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> list[str]:
    return await service.reconcile(
        db, namespace=namespace, slug=slug, schema=request.app.state.grid_schema
    )


# ── Rows ────────────────────────────────────────────────────────────────────────


@router.post("/tables/{slug}/rows", response_model=schemas.RowOut, status_code=201)
async def create_row(
    slug: str,
    body: schemas.RowCreate,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> schemas.RowOut:
    row = await service.add_row(db, namespace=namespace, slug=slug, body=body)
    return schemas.RowOut(id=row.id, payload=row.payload)


@router.get("/rows/{row_id}", response_model=schemas.RowOut)
async def get_row(
    row_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> schemas.RowOut:
    row = await service.read_row(db, row_id=row_id)
    return schemas.RowOut(id=row.id, payload=row.payload)


@router.patch("/rows/{row_id}", response_model=schemas.RowOut)
async def patch_row(
    row_id: uuid.UUID, body: schemas.RowPatch, db: AsyncSession = Depends(get_db)
) -> schemas.RowOut:
    row = await service.update_row(db, row_id=row_id, body=body)
    return schemas.RowOut(id=row.id, payload=row.payload)


@router.delete("/rows/{row_id}", status_code=204)
async def archive_row(row_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    await service.archive(db, row_id=row_id)


@router.post("/tables/{slug}/query", response_model=schemas.QueryResult)
async def query(
    slug: str,
    body: schemas.QueryRequest | None = None,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> schemas.QueryResult:
    return await service.query(
        db, namespace=namespace, slug=slug, body=body or schemas.QueryRequest()
    )


@router.post("/tables/{slug}/rows/{row_id}/relate", status_code=204)
async def relate(
    slug: str,
    row_id: uuid.UUID,
    body: schemas.RelateRequest,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> None:
    await service.relate(db, namespace=namespace, slug=slug, row_id=row_id, body=body)


@router.get("/tables/{slug}/rows/{row_id}/links", response_model=list[schemas.RowOut])
async def list_links(
    slug: str,
    row_id: uuid.UUID,
    relation_key: str,
    db: AsyncSession = Depends(get_db),
    namespace: str = Depends(get_namespace),
) -> list[schemas.RowOut]:
    rows = await service.list_links(
        db, namespace=namespace, slug=slug, row_id=row_id, relation_key=relation_key
    )
    return [schemas.RowOut(id=r.id, payload=r.payload) for r in rows]


__all__ = ["router", "get_db", "get_namespace"]
