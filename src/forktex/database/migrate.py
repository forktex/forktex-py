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

"""Generic SQL-file migration runner for library-owned Postgres schemas.

For library-owned schemas that live outside a consumer's own alembic scope
(e.g. a ``forktex_flow.*`` / ``forktex_grid.*`` substrate). Consumer services
keep their own alembic; this runner manages only the library schemas.

Convention: migration files are named ``v{NNNN}__{description}.sql``,
sorted by the integer prefix, applied in order. Each file may contain
multiple statements; the runner uses asyncpg's simple-query protocol
to execute the whole script in one transaction.

The version log lives in ``{schema}.schema_version``. The schema itself
is created if absent. Everything runs under a Postgres advisory lock so
concurrent workers (common on cold-start) serialise without racing DDL.

Usage::

    from pathlib import Path
    from forktex.database.migrate import SchemaMigrationRunner

    runner = SchemaMigrationRunner(
        engine=engine,
        schema="forktex_flow",
        migrations_dir=Path(__file__).parent / "migrations",
    )
    await runner.apply()

    # With schema_translate_map (public schema + prefix via SQLAlchemy):
    runner = SchemaMigrationRunner(
        engine=engine,
        schema="forktex_flow",          # logical name
        migrations_dir=...,
        target_schema="public",         # override where DDL actually runs
    )
"""

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
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = get_logger(__name__)


class SchemaMigrationRunner:
    """Idempotent, multi-worker-safe SQL migration runner.

    Args:
        engine: Async SQLAlchemy engine.
        schema: Logical schema name (e.g. ``"forktex_flow"``). Also used
                as the DDL target unless ``target_schema`` is set.
        migrations_dir: Directory containing ``v{NNNN}__*.sql`` files.
        target_schema: If set, DDL runs in this schema instead of
                       ``schema`` — enables ``schema_translate_map``
                       style deployments where everything lives in
                       ``"public"`` with the version table there too.
    """

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
        # `advisory_key`, not a local crc32: it is the one place that folds a digest
        # into Postgres's signed bigint range, and a second implementation of the
        # same mechanic is what `code-reuse.md` rule 6 forbids. Keyed on schema +
        # table so different library schemas never contend on one lock.
        self._lock_key = advisory_key(schema, version_table, "migrations")

    def _list_migrations(self) -> list[tuple[int, Path]]:
        """Return all ``v{NNNN}__*.sql`` files sorted by version number."""
        out: list[tuple[int, Path]] = []
        for path in self._migrations_dir.glob("v*.sql"):
            m = re.match(r"^v(\d+)__.*\.sql$", path.name)
            if not m:
                continue
            out.append((int(m.group(1)), path))
        out.sort(key=lambda x: x[0])
        return out

    async def apply(self) -> None:
        """Apply all unapplied migrations under an advisory lock.

        Safe to call from every worker on startup — concurrent callers
        serialise on the advisory lock; the first applies, the rest
        skip already-applied versions.
        """
        async with advisory_lock(self._engine, self._lock_key):
            await self._bootstrap()
            await self._apply_pending()

    def _version_table_construct(self) -> sa.Table:
        """The version-tracking table as a Core ``Table``.

        Built here rather than interpolated into SQL text: the dialect's preparer
        quotes ``schema``/``table`` (``data-access.md`` rule 4), so a hostile
        identifier is escaped rather than merely regex-screened, and the same
        construct drives the DDL, the SELECT and the INSERT below — one
        definition, three uses, no chance of them drifting.

        A fresh ``MetaData`` each call: this table is infrastructure for the
        runner, and must never join a consumer's registry.
        """
        return sa.Table(
            self._version_table,
            sa.MetaData(),
            # autoincrement=False keeps this INTEGER — Core renders a SERIAL for
            # an integer primary key otherwise, and the version is supplied.
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
        """Create the schema and version-tracking table if absent."""
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
        target = self._target
        for version, path in self._list_migrations():
            if version in applied:
                continue
            # SQL files may use {schema} as a placeholder so a single file
            # can target different schema names at runtime. A plain string
            # replace (not str.format) — migration SQL routinely contains
            # literal `{`/`}` (JSONB defaults, PL/pgSQL blocks) that
            # str.format would try to parse as fields and choke on.
            sql = path.read_text(encoding="utf-8").replace("{schema}", target)
            logger.info(
                "%s: applying migration v%04d (%s)",
                self._schema,
                version,
                path.name,
            )
            async with self._engine.begin() as conn:
                # asyncpg can't run multi-statement scripts via the
                # prepared-statement protocol; drop to raw asyncpg which
                # uses the simple-query protocol and accepts whole scripts.
                raw = await conn.get_raw_connection()
                asyncpg_conn = raw.driver_connection
                if asyncpg_conn is None:
                    raise ServiceUnavailableError("Failed to obtain raw asyncpg connection for migration DDL")
                await asyncpg_conn.execute(sql)
                await conn.execute(sa.insert(self._version_table_construct()).values(version=version))


__all__ = ["SchemaMigrationRunner"]
