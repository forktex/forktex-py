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


from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine
import asyncio
from pathlib import Path

import pytest

from forktex.error import BadRequestError
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

MIGRATION_SQL = """\
CREATE TABLE IF NOT EXISTS "{schema}".test_items (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);
"""


async def _table_exists(engine: AsyncEngine, schema: str, table: str) -> bool:
    async with engine.connect() as conn:
        found = await conn.execute(sa.select(sa.func.to_regclass(f'"{schema}".{table}')))
        return found.scalar_one() is not None


def _make_migrations_dir(tmp_path: Path) -> Path:
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "v0001__create_items.sql").write_text(MIGRATION_SQL)
    return mdir


@pytest.mark.asyncio
async def test_apply_creates_schema_and_table(postgres_url_str: str, fresh_schema: str, tmp_path: Path) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    engine = create_async_engine(postgres_url_str)
    mdir = _make_migrations_dir(tmp_path)
    runner = SchemaMigrationRunner(engine, schema=fresh_schema, migrations_dir=mdir)
    await runner.apply()

    assert await _table_exists(engine, fresh_schema, "test_items")
    await engine.dispose()


@pytest.mark.asyncio
async def test_apply_idempotent(postgres_url_str: str, fresh_schema: str, tmp_path: Path) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    engine = create_async_engine(postgres_url_str)
    mdir = _make_migrations_dir(tmp_path)
    runner = SchemaMigrationRunner(engine, schema=fresh_schema, migrations_dir=mdir)
    await runner.apply()
    await runner.apply()

    async with engine.connect() as conn:
        count = (await conn.execute(sa.text(f'SELECT COUNT(*) FROM "{fresh_schema}".schema_version'))).scalar_one()
    assert count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_apply_concurrent_workers_safe(postgres_url_str: str, fresh_schema: str, tmp_path: Path) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    mdir = _make_migrations_dir(tmp_path)

    async def run_one() -> None:
        engine = create_async_engine(postgres_url_str)
        runner = SchemaMigrationRunner(engine, schema=fresh_schema, migrations_dir=mdir)
        await runner.apply()
        await engine.dispose()

    await asyncio.gather(run_one(), run_one())

    engine = create_async_engine(postgres_url_str)
    async with engine.connect() as conn:
        count = (await conn.execute(sa.text(f'SELECT COUNT(*) FROM "{fresh_schema}".schema_version'))).scalar_one()
    assert count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_apply_migration_with_literal_braces_in_sql(
    postgres_url_str: str, fresh_schema: str, tmp_path: Path
) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "v0001__create_items.sql").write_text(
        """\
CREATE TABLE IF NOT EXISTS "{schema}".braces_items (
    id       SERIAL PRIMARY KEY,
    payload  JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""
    )
    engine = create_async_engine(postgres_url_str)
    runner = SchemaMigrationRunner(engine, schema=fresh_schema, migrations_dir=mdir)
    await runner.apply()

    assert await _table_exists(engine, fresh_schema, "braces_items")
    await engine.dispose()


def test_invalid_schema_identifier_raises(tmp_path: Path) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    mdir = tmp_path / "migrations"
    mdir.mkdir()
    engine = create_async_engine("postgresql+asyncpg://unused/unused")
    with pytest.raises(BadRequestError, match="unsafe schema name"):
        SchemaMigrationRunner(engine, schema="bad; drop table x", migrations_dir=mdir)


def test_missing_migrations_dir_raises(tmp_path: Path) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    engine = create_async_engine("postgresql+asyncpg://unused/unused")
    with pytest.raises(BadRequestError, match="does not exist"):
        SchemaMigrationRunner(engine, schema="valid_schema", migrations_dir=tmp_path / "nope")


@pytest.mark.asyncio
async def test_apply_target_schema_override(postgres_url_str: str, fresh_schema: str, tmp_path: Path) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    engine = create_async_engine(postgres_url_str)
    target = fresh_schema + "_target"
    async with engine.begin() as conn:
        await conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{target}"'))

    mdir = _make_migrations_dir(tmp_path)
    runner = SchemaMigrationRunner(engine, schema="logical_name", migrations_dir=mdir, target_schema=target)
    await runner.apply()

    assert await _table_exists(engine, target, "test_items")
    assert not await _table_exists(engine, "logical_name", "test_items")
    await engine.dispose()


def test_version_table_ddl_is_built_by_core_not_string_interpolation() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from forktex.database.migrate import SchemaMigrationRunner

    engine = sa.ext.asyncio.create_async_engine("postgresql+asyncpg://nobody@nowhere.invalid/x")
    runner = SchemaMigrationRunner(
        engine,
        schema="forktex_probe",
        migrations_dir=Path(__file__).parent,
    )
    table = runner._version_table_construct()
    rendered = str(CreateTable(table, if_not_exists=True).compile(dialect=postgresql.dialect()))

    assert "CREATE TABLE IF NOT EXISTS forktex_probe.schema_version" in rendered
    assert "version INTEGER NOT NULL" in rendered
    assert "SERIAL" not in rendered
    assert "TIMESTAMP WITH TIME ZONE" in rendered


def test_runners_sharing_a_version_table_share_a_lock() -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    engine = create_async_engine("postgresql+asyncpg://nobody@nowhere.invalid/x")
    here = Path(__file__).parent
    flow = SchemaMigrationRunner(engine, schema="forktex_flow", migrations_dir=here, target_schema="public")
    grid = SchemaMigrationRunner(engine, schema="forktex_grid", migrations_dir=here, target_schema="public")
    assert flow._lock_key == grid._lock_key


@pytest.mark.asyncio
async def test_a_migration_and_its_version_row_commit_in_one_transaction(
    postgres_url_str: str, fresh_schema: str, tmp_path: Path
) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "v0001__probe.sql").write_text(
        'CREATE TABLE "{schema}".probe (txid bigint);\nINSERT INTO "{schema}".probe VALUES (txid_current());\n'
    )
    engine = create_async_engine(postgres_url_str)
    await SchemaMigrationRunner(engine, schema=fresh_schema, migrations_dir=mdir).apply()

    async with engine.connect() as conn:
        script_txid = (await conn.execute(sa.text(f'SELECT txid FROM "{fresh_schema}".probe'))).scalar_one()
        version_txid = (
            await conn.execute(sa.text(f'SELECT xmin::text::bigint FROM "{fresh_schema}".schema_version'))
        ).scalar_one()
    assert script_txid == version_txid
    await engine.dispose()


@pytest.mark.parametrize("names", [["v1_missing_separator.sql"], ["v0001__a.sql", "v1__b.sql"]])
def test_misnamed_or_duplicate_migrations_are_refused(tmp_path: Path, names: list[str]) -> None:
    from forktex.database.migrate import SchemaMigrationRunner

    for name in names:
        (tmp_path / name).write_text("SELECT 1;")
    runner = SchemaMigrationRunner(
        create_async_engine("postgresql+asyncpg://nobody@nowhere.invalid/x"),
        schema="forktex_probe",
        migrations_dir=tmp_path,
    )
    with pytest.raises(BadRequestError, match="named|share version"):
        runner._list_migrations()


@pytest.mark.asyncio
async def test_a_failing_migration_raises_a_named_error_and_records_no_version(
    postgres_url_str: str, fresh_schema: str, tmp_path: Path
) -> None:
    """A broken statement raised a raw asyncpg exception carrying driver text,
    and nothing proved the version row rolled back with it."""
    from forktex.database.errors import MigrationError
    from forktex.database.migrate import SchemaMigrationRunner

    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "v0001__half_broken.sql").write_text(
        'CREATE TABLE "{schema}".first_half (id SERIAL PRIMARY KEY);\n'
        'INSERT INTO "{schema}".a_table_that_does_not_exist (id) VALUES (1);\n'
    )

    engine = create_async_engine(postgres_url_str)
    runner = SchemaMigrationRunner(engine, schema=fresh_schema, migrations_dir=mdir)

    with pytest.raises(MigrationError) as raised:
        await runner.apply()

    assert "v0001__half_broken.sql" in str(raised.value)
    assert "a_table_that_does_not_exist" not in str(raised.value)
    assert raised.value.__cause__ is not None

    assert not await _table_exists(engine, fresh_schema, "first_half")
    async with engine.connect() as conn:
        recorded = await conn.execute(sa.text(f'SELECT count(*) FROM "{fresh_schema}".schema_version'))
        assert recorded.scalar_one() == 0
    await engine.dispose()
