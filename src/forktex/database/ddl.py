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

from sqlalchemy import Column
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import (
    CreateIndex,
    CreateSchema,
    CreateTable,
    DDLElement,
    DropIndex,
    DropSchema,
    DropTable,
)
from sqlalchemy.sql.compiler import DDLCompiler

__all__ = [
    "AddColumn",
    "CreateIndex",
    "CreateSchema",
    "CreateTable",
    "DropColumn",
    "DropIndex",
    "DropSchema",
    "DropTable",
]


class AddColumn(DDLElement):
    inherit_cache = False

    def __init__(self, column: Column, *, if_not_exists: bool = False) -> None:
        if column.table is None:
            raise ValueError("AddColumn requires a column attached to a Table")
        self.column = column
        self.if_not_exists = if_not_exists


class DropColumn(DDLElement):
    inherit_cache = False

    def __init__(
        self,
        table_name: str,
        column_name: str,
        *,
        schema: str | None = None,
        if_exists: bool = False,
    ) -> None:
        self.table_name = table_name
        self.column_name = column_name
        self.schema = schema
        self.if_exists = if_exists


def _qualified(compiler: DDLCompiler, table_name: str, schema: str | None) -> str:
    preparer = compiler.preparer
    quoted = preparer.quote(table_name)
    return f"{preparer.quote_schema(schema)}.{quoted}" if schema else quoted


@compiles(AddColumn)
def _compile_add_column(element: AddColumn, compiler: DDLCompiler, **kw: object) -> str:
    column = element.column
    table = column.table
    target = _qualified(compiler, table.name, table.schema)
    exists = "IF NOT EXISTS " if element.if_not_exists else ""
    return f"ALTER TABLE {target} ADD COLUMN {exists}{compiler.get_column_specification(column)}"


@compiles(DropColumn)
def _compile_drop_column(element: DropColumn, compiler: DDLCompiler, **kw: object) -> str:
    target = _qualified(compiler, element.table_name, element.schema)
    exists = "IF EXISTS " if element.if_exists else ""
    return f"ALTER TABLE {target} DROP COLUMN {exists}{compiler.preparer.quote(element.column_name)}"
