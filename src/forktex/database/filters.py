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

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, ClassVar, Protocol, runtime_checkable

import sqlalchemy as sa

from forktex.error import BadRequestError
from forktex.types import BaseValueObject, BaseWireValueObject

MAX_FILTER_DEPTH = 50

MAX_IN_ITEMS = 1000


class FilterOp(StrEnum):
    eq = "eq"
    ne = "ne"
    lt = "lt"
    lte = "lte"
    gt = "gt"
    gte = "gte"
    in_ = "in"
    not_in = "not_in"
    contains = "contains"
    icontains = "icontains"
    starts_with = "startswith"
    ends_with = "endswith"
    between = "between"
    is_null = "is_null"
    fuzzy = "fuzzy"


LIKE_OPS = frozenset({FilterOp.contains, FilterOp.icontains, FilterOp.starts_with, FilterOp.ends_with})


class SortDirection(StrEnum):
    asc = "asc"
    desc = "desc"


class SortKey(BaseWireValueObject):
    column: str
    direction: SortDirection = SortDirection.asc

    @classmethod
    def parse(cls, obj: SortKey | Mapping[str, str]) -> SortKey:
        if isinstance(obj, SortKey):
            return obj
        if not isinstance(obj, Mapping) or not isinstance(obj.get("column"), str):
            raise BadRequestError(f"malformed sort key: {obj!r}")
        try:
            direction = SortDirection(str(obj.get("direction", "asc")).lower())
        except ValueError:
            raise BadRequestError(f"invalid sort direction {obj.get('direction')!r}") from None
        return cls(column=obj["column"], direction=direction)


class Comparison(BaseValueObject):
    column: str
    op: FilterOp
    value: Any = None


class And(BaseValueObject):
    __match_args__: ClassVar[tuple[str, ...]] = ("children",)

    children: tuple[FilterNode, ...]


class Or(BaseValueObject):
    __match_args__: ClassVar[tuple[str, ...]] = ("children",)

    children: tuple[FilterNode, ...]


class Not(BaseValueObject):
    __match_args__: ClassVar[tuple[str, ...]] = ("child",)

    child: FilterNode


FilterNode = And | Or | Not | Comparison

And.model_rebuild()
Or.model_rebuild()
Not.model_rebuild()
Comparison.model_rebuild()


def parse_filter(obj: FilterNode | Mapping[str, Any], *, _depth: int = 0) -> FilterNode:
    if isinstance(obj, (And, Or, Not, Comparison)):
        return obj
    if not isinstance(obj, Mapping):
        raise BadRequestError(f"malformed filter node: {obj!r}")
    if _depth > MAX_FILTER_DEPTH:
        raise BadRequestError(f"filter nesting exceeds {MAX_FILTER_DEPTH} levels")
    if "and" in obj:
        return And(children=_parse_children(obj, "and", _depth))
    if "or" in obj:
        return Or(children=_parse_children(obj, "or", _depth))
    if "not" in obj:
        return Not(child=parse_filter(obj["not"], _depth=_depth + 1))
    if not isinstance(obj.get("column"), str) or "op" not in obj:
        raise BadRequestError(f"malformed filter node: {obj!r}")
    try:
        op = FilterOp(obj["op"])
    except ValueError:
        raise BadRequestError(f"unknown operator {obj['op']!r}") from None
    return Comparison(column=obj["column"], op=op, value=obj.get("value"))


@runtime_checkable
class FilterSource(Protocol):
    def check(self, column: str, op: FilterOp) -> None: ...

    def raw_expr(self, column: str) -> sa.ColumnElement[Any]: ...

    def typed_expr(self, column: str) -> sa.ColumnElement[Any]: ...

    def operand(self, column: str, value: object) -> sa.ColumnElement[Any]: ...

    def like_lhs(self, column: str) -> sa.ColumnElement[Any]: ...


class ColumnSource:
    def __init__(self, entity: object, *, allowed: set[str] | None = None) -> None:
        self._entity = entity
        self._allowed = allowed

    def _column(self, column: str) -> sa.ColumnElement[Any]:
        if self._allowed is not None and column not in self._allowed:
            raise BadRequestError(f"column {column!r} is not filterable")
        if column not in sa.inspect(self._entity, raiseerr=True).mapper.column_attrs:
            raise BadRequestError(f"unknown column {column!r}")
        return getattr(self._entity, column)

    def check(self, column: str, op: FilterOp) -> None:
        self._column(column)

    def raw_expr(self, column: str) -> sa.ColumnElement[Any]:
        return self._column(column)

    def typed_expr(self, column: str) -> sa.ColumnElement[Any]:
        return self._column(column)

    def operand(self, column: str, value: object) -> sa.ColumnElement[Any]:
        return sa.literal(value)

    def like_lhs(self, column: str) -> sa.ColumnElement[Any]:
        return sa.cast(self._column(column), sa.Text)


def compile_filter(node: FilterNode, source: FilterSource) -> sa.ColumnElement[bool]:
    match node:
        case And(children=children):
            return sa.and_(*(compile_filter(c, source) for c in children))
        case Or(children=children):
            return sa.or_(*(compile_filter(c, source) for c in children))
        case Not(child=child):
            return sa.not_(compile_filter(child, source))
        case Comparison():
            return compile_comparison(node, source)
    raise BadRequestError(f"unsupported filter node: {node!r}")


def compile_comparison(node: Comparison, source: FilterSource) -> sa.ColumnElement[bool]:
    column, op, value = node.column, node.op, node.value
    source.check(column, op)

    if op is FilterOp.is_null:
        if value is not None and not isinstance(value, bool):
            raise BadRequestError("'is_null' takes true or false")
        want_null = value is not False
        expr = source.raw_expr(column)
        return expr.is_(None) if want_null else expr.isnot(None)

    if op is FilterOp.fuzzy:
        return source.like_lhs(column).op("%")(str(value))

    if op in LIKE_OPS:
        lhs = source.like_lhs(column)
        pattern = _like_pattern(op, value)
        return lhs.ilike(pattern, escape="\\") if op is FilterOp.icontains else lhs.like(pattern, escape="\\")

    if op in (FilterOp.in_, FilterOp.not_in):
        if not isinstance(value, list):
            raise BadRequestError(f"'{op.value}' takes a list")
        items = value
        if len(items) > MAX_IN_ITEMS:
            raise BadRequestError(f"'{op.value}' list exceeds {MAX_IN_ITEMS} items")
        rhs = [source.operand(column, v) for v in items]
        expr = source.typed_expr(column)
        return expr.notin_(rhs) if op is FilterOp.not_in else expr.in_(rhs)

    if op is FilterOp.between:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise BadRequestError("'between' requires [low, high]")
        return source.typed_expr(column).between(source.operand(column, value[0]), source.operand(column, value[1]))

    lhs, rhs = source.typed_expr(column), source.operand(column, value)
    return {
        FilterOp.eq: lhs == rhs,
        FilterOp.ne: lhs != rhs,
        FilterOp.lt: lhs < rhs,
        FilterOp.lte: lhs <= rhs,
        FilterOp.gt: lhs > rhs,
        FilterOp.gte: lhs >= rhs,
    }[op]


def _parse_children(obj: Mapping[str, Any], key: str, depth: int) -> tuple[FilterNode, ...]:
    children = obj[key]
    if not isinstance(children, list):
        raise BadRequestError(f"'{key}' filter takes a list")
    if not children:
        raise BadRequestError(f"empty '{key}' filter")
    return tuple(parse_filter(child, _depth=depth + 1) for child in children)


def _like_pattern(op: FilterOp, value: object) -> str:
    term = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return {
        FilterOp.contains: f"%{term}%",
        FilterOp.icontains: f"%{term}%",
        FilterOp.starts_with: f"{term}%",
        FilterOp.ends_with: f"%{term}",
    }[op]


__all__ = [
    "LIKE_OPS",
    "MAX_FILTER_DEPTH",
    "MAX_IN_ITEMS",
    "And",
    "ColumnSource",
    "Comparison",
    "FilterNode",
    "FilterOp",
    "FilterSource",
    "Not",
    "Or",
    "SortDirection",
    "SortKey",
    "compile_comparison",
    "compile_filter",
    "parse_filter",
]
