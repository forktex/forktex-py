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


"""Grid-dependent half of the temporal-standard suite.

Split out of tests/test_database/test_temporal_standard.py when grid moved to
backlog: these assert the *physical* schema grid's real SQL migrations produce,
so they cannot run without grid. Fold them back in when grid returns.
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
import sqlalchemy as sa
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from forktex.database import reflect
from forktex.database.models import AuditMixin, BaseDBModel, TimestampMixin, UtcDateTime
from forktex.iso import now

# ---------------------------------------------------------------------------
# Physically-created schema (requires Postgres)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def grid_schema_engine(postgres_url_str: str, fresh_schema: str):
    """Apply grid's real migrations into a fresh schema."""
    from forktex.grid import apply_migrations

    engine = create_async_engine(postgres_url_str)
    async with engine.begin() as conn:
        await conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{fresh_schema}"'))
    await apply_migrations(engine, schema=fresh_schema)
    yield engine, fresh_schema
    await engine.dispose()


@pytest.mark.asyncio
async def test_grid_migrations_produce_only_tz_aware_temporal_columns(grid_schema_engine):
    """v0001 declared `created_at`/`updated_at` as naive `timestamp`;
    v0002 converts them. Reflected here so the *physical* schema is asserted,
    not just the ORM's opinion of it."""
    engine, schema = grid_schema_engine
    tables = [
        "grid_space",
        "grid_table",
        "grid_relation",
        "grid_column",
        "grid_index",
        "grid_row",
        "grid_edge",
    ]
    offenders = []
    async with engine.connect() as conn:
        for table in tables:
            for name, type_ in (await reflect.column_types(conn, table, schema=schema)).items():
                if isinstance(type_, sa.DateTime) and not type_.timezone:
                    offenders.append(f"{table}.{name}")
    assert offenders == [], f"naive temporal columns: {offenders}"

    # ...and prove v0002 is what made that true, rather than the test passing
    # vacuously: v0001 creates these columns naive.
    async with engine.connect() as conn:
        applied = [
            r[0] for r in await conn.execute(sa.text(f'SELECT version FROM "{schema}".schema_version ORDER BY version'))
        ]
    assert applied == [1, 2], applied


@pytest.mark.asyncio
async def test_an_iso_aware_datetime_round_trips_through_a_grid_column(grid_schema_engine):
    """The end-to-end invariant: what `iso` produces can be written and read
    back as the same instant. On a naive column asyncpg rejects the write.
    """
    engine, schema = grid_schema_engine
    # An instant expressed with a non-UTC offset, as an external caller might.
    supplied = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                f'INSERT INTO "{schema}".grid_space (id, namespace, slug, label, created_at) '
                "VALUES (gen_random_uuid(), 'ns', 'tz-probe', 'TZ Probe', :at)"
            ),
            {"at": supplied},
        )
        stored = (
            await conn.execute(sa.text(f"SELECT created_at FROM \"{schema}\".grid_space WHERE slug = 'tz-probe'"))
        ).scalar_one()

    assert stored.tzinfo is not None, "offset was discarded"
    assert stored == supplied, "not the same instant"
    # normalised to UTC on the way in, matching iso.to_iso's output shape
    assert stored.utcoffset() == timedelta(0)


@pytest.mark.asyncio
async def test_iso_now_is_writable_to_a_grid_column(grid_schema_engine):
    """`iso.now()` is UTC-aware; writing it must not raise. This is the case a
    naive column made impossible."""
    engine, schema = grid_schema_engine
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                f'INSERT INTO "{schema}".grid_space (id, namespace, slug, label, created_at, updated_at) '
                "VALUES (gen_random_uuid(), 'ns', 'iso-now', 'ISO Now', :at, :at2)"
            ),
            {"at": now(), "at2": now()},
        )
