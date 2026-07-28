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

"""Pydantic DTOs for the grid HTTP interface.

These mirror the ``forktex_core.grid`` model (tables / columns / sections /
relations / indexes / rows) and the type registry. The ``*Out`` shapes carry
``capabilities`` so the frontend is fully driven by the server's declared
state space.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ── Type registry ────────────────────────────────────────────────────────────


class Capabilities(_Base):
    filterable: bool
    sortable: bool
    fuzzy: bool
    cursor_browsable: bool
    filter_ops: list[str]
    index_kinds: list[str]
    default_index_kind: str | None = None


class TypeDescriptor(_Base):
    """A field type's built-in capabilities + per-column config schema.

    Drives dynamic form/filter rendering in the studio.
    """

    type_id: str
    capabilities: Capabilities
    config_schema: dict[str, Any]


# ── Tables ────────────────────────────────────────────────────────────────────


class TableCreate(_Base):
    slug: str
    label: str
    ownership: Literal["owned", "bound"] = "owned"
    projection_predicate: dict[str, Any] | None = None
    natural_key: list[str] | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class TableOut(_Base):
    id: uuid.UUID
    namespace: str
    slug: str
    label: str
    ownership: str
    projection_predicate: dict[str, Any] | None = None
    natural_key: list[str] | None = None


# ── Columns ────────────────────────────────────────────────────────────────────


class ColumnCreate(_Base):
    key: str
    label: str
    type_id: str
    cardinality: Literal["one", "many"] = "one"
    materialization: Literal["payload", "promoted", "derived"] = "payload"
    is_required: bool = False
    is_unique: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    default_value: Any = None
    display_order: int = 0
    # For a ``ref`` column: the key of a relation already declared on this table.
    relation_key: str | None = None


class ColumnOut(_Base):
    id: uuid.UUID
    key: str
    label: str
    type_id: str
    cardinality: str
    materialization: str
    is_required: bool
    is_unique: bool
    display_order: int
    config: dict[str, Any]
    capabilities: Capabilities


# ── Sections ───────────────────────────────────────────────────────────────────


class SectionCreate(_Base):
    slug: str
    label: str
    is_default: bool = False
    row_filter: dict[str, Any] | None = None
    sort_spec: list[dict[str, Any]] | None = None
    browse_mode: Literal["page", "cursor"] = "page"


class SectionOut(_Base):
    id: uuid.UUID
    slug: str
    label: str
    is_default: bool
    browse_mode: str
    row_filter: dict[str, Any] | None = None
    sort_spec: list[dict[str, Any]] | None = None


# ── Relations ──────────────────────────────────────────────────────────────────


class RelationCreate(_Base):
    key: str
    target_slug: str
    relation_type: Literal["one_to_one", "one_to_many", "many_to_many"]
    through_slug: str | None = None
    direction: Literal["outbound", "inbound"] = "outbound"
    on_delete: Literal["restrict", "cascade", "set_null"] = "restrict"


class RelationOut(_Base):
    id: uuid.UUID
    key: str
    relation_type: str
    direction: str
    on_delete: str
    source_table_id: uuid.UUID
    target_table_id: uuid.UUID
    through_table_id: uuid.UUID | None = None


# ── Indexes ────────────────────────────────────────────────────────────────────


class IndexCreate(_Base):
    column_keys: list[str]
    index_kind: str = "btree"
    is_unique: bool = False


class IndexOut(_Base):
    id: uuid.UUID
    column_keys: list[str]
    index_kind: str
    is_unique: bool
    state: str
    physical_name: str | None = None


# ── Describe (the table's full state space) ─────────────────────────────────────


class TableDescribe(_Base):
    table: TableOut
    columns: list[ColumnOut]
    sections: list[SectionOut]
    relations: list[RelationOut]
    indexes: list[IndexOut]


# ── Rows ────────────────────────────────────────────────────────────────────────


class RowCreate(_Base):
    values: dict[str, Any] = Field(default_factory=dict)


class RowPatch(_Base):
    values: dict[str, Any] = Field(default_factory=dict)


class RowOut(_Base):
    id: uuid.UUID
    payload: dict[str, Any]


class RelateRequest(_Base):
    relation_key: str
    target_row_id: uuid.UUID
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Query ──────────────────────────────────────────────────────────────────────


class QueryRequest(_Base):
    filter: dict[str, Any] | None = None
    sort: list[dict[str, str]] | None = None
    mode: Literal["page", "cursor"] = "page"
    limit: int = 50
    offset: int = 0
    cursor: str | None = None
    include_total: bool = False


class QueryResult(_Base):
    rows: list[RowOut]
    next_cursor: str | None = None
    total: int | None = None


__all__ = [
    "Capabilities",
    "TypeDescriptor",
    "TableCreate",
    "TableOut",
    "ColumnCreate",
    "ColumnOut",
    "SectionCreate",
    "SectionOut",
    "RelationCreate",
    "RelationOut",
    "IndexCreate",
    "IndexOut",
    "TableDescribe",
    "RowCreate",
    "RowPatch",
    "RowOut",
    "RelateRequest",
    "QueryRequest",
    "QueryResult",
]
