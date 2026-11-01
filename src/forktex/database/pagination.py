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

import base64
import json
from typing import Any

import sqlalchemy as sa
from pydantic import Field

from forktex.error import BadRequestError
from forktex.types import BaseAppModel


class Page[T](BaseAppModel):
    items: list[T] = Field(default_factory=list)
    has_more: bool = False
    next_cursor: str | None = None
    total: int | None = None


def encode_cursor(values: list[Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(values, default=str).encode()).decode()


def decode_cursor(cursor: str, *, expected_length: int | None = None) -> list[Any]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        values = json.loads(raw.decode())
    except (ValueError, TypeError) as exc:
        raise BadRequestError("invalid cursor") from exc
    if not isinstance(values, list):
        raise BadRequestError("invalid cursor")
    if expected_length is not None and len(values) != expected_length:
        raise BadRequestError("invalid cursor")
    return values


def keyset_predicate(
    levels: list[tuple[sa.SQLColumnExpression[Any], Any]],
    *,
    ascending: bool,
) -> sa.ColumnElement[bool]:
    if not levels:
        raise ValueError("keyset_predicate requires at least one level")

    def _eq(expr: sa.SQLColumnExpression[Any], value: object) -> sa.ColumnElement[bool]:
        return expr.is_(None) if value is None else (expr == value)

    disjuncts: list[sa.ColumnElement[bool]] = []
    for i, (expr, value) in enumerate(levels):
        after = _sorts_after(expr, value, ascending=ascending, is_tiebreaker=i == len(levels) - 1)
        if after is not None:
            disjuncts.append(sa.and_(*[_eq(e, v) for e, v in levels[:i]], after))

    if not disjuncts:
        raise BadRequestError("invalid cursor")
    return sa.or_(*disjuncts)


def _sorts_after(
    expr: sa.SQLColumnExpression[Any], value: object, *, ascending: bool, is_tiebreaker: bool
) -> sa.ColumnElement[bool] | None:
    nulls_last = ascending
    if value is None:
        return None if nulls_last else expr.is_not(None)
    if not ascending:
        return expr < value
    if is_tiebreaker:
        return expr > value
    return sa.or_(expr > value, expr.is_(None))


__all__ = [
    "Page",
    "decode_cursor",
    "encode_cursor",
    "keyset_predicate",
]
