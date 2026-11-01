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

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.types import TypeEngine


async def columns(executor: _Executor, relation: str, *, schema: str | None = None) -> set[str]:
    return set((await column_types(executor, relation, schema=schema)).keys())


async def column_types(executor: _Executor, relation: str, *, schema: str | None = None) -> dict[str, TypeEngine[Any]]:
    embedded_schema, table = _split_relation(relation)
    target_schema = schema or embedded_schema

    def _reflect(conn: Connection) -> dict[str, TypeEngine[Any]]:
        insp = inspect(conn)
        if not insp.has_table(table, schema=target_schema):
            return {}
        return {str(col["name"]): col["type"] for col in insp.get_columns(table, schema=target_schema)}

    result = await _run_sync(executor, _reflect)
    return dict(result)


def type_ddl(type_: TypeEngine[Any]) -> str:
    return str(type_.compile(dialect=postgresql.dialect()))


async def has_table(executor: _Executor, relation: str, *, schema: str | None = None) -> bool:
    embedded_schema, table = _split_relation(relation)
    target_schema = schema or embedded_schema

    def _check(conn: Connection) -> bool:
        return inspect(conn).has_table(table, schema=target_schema)

    return bool(await _run_sync(executor, _check))


async def udt_names(executor: _Executor, relation: str, *, schema: str | None = None) -> dict[str, str]:
    embedded_schema, table = _split_relation(relation)
    target_schema = schema or embedded_schema
    stmt = sa.text(
        "SELECT column_name, udt_name FROM information_schema.columns "
        "WHERE table_name = :t AND table_schema = COALESCE(:s, current_schema())"
    )
    result = await executor.execute(stmt, {"t": table, "s": target_schema})
    return {row.column_name: row.udt_name for row in result}


async def indexes(executor: _Executor, relation: str, *, schema: str | None = None) -> set[str]:
    embedded_schema, table = _split_relation(relation)
    target_schema = schema or embedded_schema

    def _reflect(conn: Connection) -> set[str]:
        insp: Inspector = inspect(conn)
        if not insp.has_table(table, schema=target_schema):
            return set()
        return {str(idx["name"]) for idx in insp.get_indexes(table, schema=target_schema) if idx.get("name")}

    return set(await _run_sync(executor, _reflect))


_Executor = AsyncSession | AsyncConnection


async def _run_sync[R](executor: _Executor, fn: Callable[[Connection], R]) -> R:
    if isinstance(executor, AsyncSession):
        return await executor.run_sync(lambda sync_session: fn(sync_session.connection()))
    return await executor.run_sync(fn)


def _split_relation(relation: str) -> tuple[str | None, str]:
    schema, _, table = relation.rpartition(".")
    return (schema or None), table


__all__ = ["column_types", "columns", "has_table", "indexes", "type_ddl", "udt_names"]
