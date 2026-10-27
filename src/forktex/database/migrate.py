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

import re
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateSchema, CreateTable

from forktex.database.identifiers import validate_identifier, validate_schema
from forktex.database.locks import advisory_key, advisory_lock
from forktex.error import BadRequestError, ServiceUnavailableError
from forktex.log import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = get_logger(__name__)

_MIGRATION_FILE = re.compile(r"^v(\d+)__.+\.sql$")


class SchemaMigrationRunner:
    def __init__(
        self,
        engine: AsyncEngine,
        schema: str,
        migrations_dir: Path,
        *,
        target_schema: str | None = None,
        version_table: str = "schema_version",
    ) -> None:
        validate_schema(schema)
        if target_schema:
            validate_schema(target_schema)
        validate_identifier(version_table, "version_table")
        if not migrations_dir.is_dir():
            raise BadRequestError(f"migrations_dir {migrations_dir!r} does not exist or isn't a directory")
        self._engine = engine
        self._schema = schema
        self._target = target_schema or schema
        self._migrations_dir = migrations_dir
        self._version_table = version_table
        self._lock_key = advisory_key(self._target, version_table, "migrations")

    def _list_migrations(self) -> list[tuple[int, Path]]:
        by_version: dict[int, Path] = {}
        for path in sorted(self._migrations_dir.glob("v*.sql")):
            version = _migration_version(path)
            if version in by_version:
                raise BadRequestError(
                    f"migrations {by_version[version].name!r} and {path.name!r} share version {version}"
                )
            by_version[version] = path
        return sorted(by_version.items())

    async def apply(self) -> None:
        async with advisory_lock(self._engine, self._lock_key):
            await self._bootstrap()
            await self._apply_pending()

    def _version_table_construct(self) -> sa.Table:
        return sa.Table(
            self._version_table,
            sa.MetaData(),
            sa.Column("version", sa.Integer, primary_key=True, autoincrement=False),
            sa.Column(
                "applied_at",
                postgresql.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            schema=self._target,
        )

    async def _bootstrap(self) -> None:
        table = self._version_table_construct()
        async with self._engine.begin() as conn:
            await conn.execute(CreateSchema(self._target, if_not_exists=True))
            await conn.execute(CreateTable(table, if_not_exists=True))

    async def _read_applied(self) -> set[int]:
        table = self._version_table_construct()
        async with self._engine.connect() as conn:
            result = await conn.execute(sa.select(table.c.version))
            return {row[0] for row in result.fetchall()}

    async def _apply_pending(self) -> None:
        applied = await self._read_applied()
        for version, path in self._list_migrations():
            if version not in applied:
                await self._apply(version, path)

    async def _apply(self, version: int, path: Path) -> None:
        logger.info("%s: applying migration v%04d (%s)", self._schema, version, path.name)
        async with self._engine.begin() as conn:
            await conn.execute(sa.insert(self._version_table_construct()).values(version=version))
            await _execute_script(conn, self._script(path))

    def _script(self, path: Path) -> str:
        return path.read_text(encoding="utf-8").replace("{schema}", self._target)


def _migration_version(path: Path) -> int:
    match = _MIGRATION_FILE.match(path.name)
    if match is None:
        raise BadRequestError(f"migration {path.name!r} is not named v{{NNNN}}__{{description}}.sql")
    return int(match.group(1))


async def _execute_script(conn: AsyncConnection, sql: str) -> None:
    raw = await conn.get_raw_connection()
    asyncpg_conn = raw.driver_connection
    if asyncpg_conn is None:
        raise ServiceUnavailableError("Failed to obtain raw asyncpg connection for migration DDL")
    await asyncpg_conn.execute(sql)


__all__ = ["SchemaMigrationRunner"]
