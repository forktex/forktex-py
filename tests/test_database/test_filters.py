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

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from forktex.database.filters import (
    MAX_FILTER_DEPTH,
    FilterNode,
    MAX_IN_ITEMS,
    And,
    ColumnSource,
    Comparison,
    FilterOp,
    Not,
    Or,
    SortDirection,
    SortKey,
    compile_filter,
    parse_filter,
)
from forktex.error import BadRequestError

_PG = postgresql.dialect()


class _Base(DeclarativeBase):
    pass


class Owner(_Base):
    __tablename__ = "owner"
    id: Mapped[int] = mapped_column(primary_key=True)


class Widget(_Base):
    __tablename__ = "widget"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(50))
    score: Mapped[int] = mapped_column(sa.Integer)
    owner_id: Mapped[int | None] = mapped_column(sa.ForeignKey("owner.id"))
    owner: Mapped[Owner | None] = relationship()


def _sql(node: FilterNode, *, allowed: set[str] | None = None) -> str:
    expr = compile_filter(node, ColumnSource(Widget, allowed=allowed))
    return " ".join(str(expr.compile(dialect=_PG, compile_kwargs={"literal_binds": True})).split())


def _params(node: FilterNode, *, allowed: set[str] | None = None) -> dict:
    expr = compile_filter(node, ColumnSource(Widget, allowed=allowed))
    return dict(expr.compile(dialect=_PG).params)


def test_parse_builds_a_nested_ast() -> None:
    node = parse_filter(
        {
            "and": [
                {"column": "name", "op": "eq", "value": "x"},
                {"or": [{"column": "score", "op": "gt", "value": 1}, {"not": {"column": "score", "op": "is_null"}}]},
            ]
        }
    )
    assert isinstance(node, And)
    assert isinstance(node.children[1], Or)
    assert isinstance(node.children[1].children[1], Not)


def test_parse_passes_a_typed_node_through() -> None:
    node = Comparison(column="name", op=FilterOp.eq, value="x")
    assert parse_filter(node) is node


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"and": []}, "empty 'and'"),
        ({"or": []}, "empty 'or'"),
        ({"column": "name"}, "malformed filter node"),
        ({"op": "eq"}, "malformed filter node"),
        ({"column": "name", "op": "NOPE"}, "unknown operator"),
        ("name", "malformed filter node"),
        ({"and": {"column": "name", "op": "eq"}}, "takes a list"),
        ({"column": ["name"], "op": "eq"}, "malformed filter node"),
    ],
)
def test_parse_rejects_malformed_input(payload: object, message: str) -> None:
    with pytest.raises(BadRequestError, match=message):
        parse_filter(payload)


def test_parse_rejects_pathological_nesting() -> None:
    deep: dict = {"column": "name", "op": "eq", "value": 1}
    for _ in range(MAX_FILTER_DEPTH + 2):
        deep = {"not": deep}
    with pytest.raises(BadRequestError, match="nesting exceeds"):
        parse_filter(deep)


def test_and_or_not_compile_structurally() -> None:
    a = Comparison(column="score", op=FilterOp.gt, value=1)
    b = Comparison(column="score", op=FilterOp.lt, value=9)
    assert _sql(And(children=(a, b))) == "widget.score > 1 AND widget.score < 9"
    assert _sql(Or(children=(a, b))) == "widget.score > 1 OR widget.score < 9"
    assert _sql(Not(child=a)) == "widget.score <= 1"


@pytest.mark.parametrize(
    "op,expected",
    [
        (FilterOp.eq, "widget.score = 5"),
        (FilterOp.ne, "widget.score != 5"),
        (FilterOp.lt, "widget.score < 5"),
        (FilterOp.lte, "widget.score <= 5"),
        (FilterOp.gt, "widget.score > 5"),
        (FilterOp.gte, "widget.score >= 5"),
    ],
)
def test_ordered_comparisons(op: FilterOp, expected: str) -> None:
    assert _sql(Comparison(column="score", op=op, value=5)) == expected


def test_is_null_truthiness() -> None:
    assert _sql(Comparison(column="name", op=FilterOp.is_null)) == "widget.name IS NULL"
    assert _sql(Comparison(column="name", op=FilterOp.is_null, value=False)) == "widget.name IS NOT NULL"


def test_between_requires_a_pair() -> None:
    assert _sql(Comparison(column="score", op=FilterOp.between, value=[1, 9])) == "widget.score BETWEEN 1 AND 9"
    with pytest.raises(BadRequestError, match=r"\[low, high\]"):
        _sql(Comparison(column="score", op=FilterOp.between, value=[1]))


def test_in_and_not_in() -> None:
    assert "widget.score IN (1, 2)" in _sql(Comparison(column="score", op=FilterOp.in_, value=[1, 2]))
    assert "widget.score NOT IN (1, 2)" in _sql(Comparison(column="score", op=FilterOp.not_in, value=[1, 2]))


@pytest.mark.parametrize("op,value", [(FilterOp.in_, "123"), (FilterOp.is_null, "false")])
def test_operand_shape_is_checked(op: FilterOp, value: str) -> None:
    with pytest.raises(BadRequestError):
        _sql(Comparison(column="score", op=op, value=value))


def test_in_list_is_bounded() -> None:
    huge = list(range(MAX_IN_ITEMS + 1))
    with pytest.raises(BadRequestError, match="exceeds"):
        _sql(Comparison(column="score", op=FilterOp.in_, value=huge))


@pytest.mark.parametrize(
    "op,pattern",
    [
        (FilterOp.contains, "%term%"),
        (FilterOp.starts_with, "term%"),
        (FilterOp.ends_with, "%term"),
    ],
)
def test_like_patterns(op: FilterOp, pattern: str) -> None:
    assert pattern in _params(Comparison(column="name", op=op, value="term")).values()


def test_icontains_uses_ilike() -> None:
    assert "ILIKE" in _sql(Comparison(column="name", op=FilterOp.icontains, value="t"))


def test_like_metacharacters_in_the_user_term_are_escaped() -> None:
    node = Comparison(column="name", op=FilterOp.contains, value="50%_x")
    assert r"%50\%\_x%" in _params(node).values()
    assert "ESCAPE" in _sql(node)


def test_fuzzy_uses_the_trigram_operator() -> None:
    assert _sql(Comparison(column="name", op=FilterOp.fuzzy, value="abc")) == "CAST(widget.name AS TEXT) %% 'abc'"


def test_compile_rejects_an_unparsed_node() -> None:
    with pytest.raises(BadRequestError, match="unsupported filter node"):
        compile_filter({"column": "name", "op": "eq"}, ColumnSource(Widget))


@pytest.mark.parametrize("column", ["nope", "owner", "metadata", "__tablename__", "_sa_class_manager"])
def test_only_mapped_columns_resolve(column: str) -> None:
    with pytest.raises(BadRequestError, match="unknown column"):
        _sql(Comparison(column=column, op=FilterOp.eq, value=1))


def test_allow_list_restricts_which_columns_are_filterable() -> None:
    node = Comparison(column="score", op=FilterOp.eq, value=1)
    assert _sql(node, allowed={"score"}) == "widget.score = 1"
    with pytest.raises(BadRequestError, match="not filterable"):
        _sql(node, allowed={"name"})


def test_sort_key_parses_dicts_and_passes_through_typed() -> None:
    assert SortKey.parse({"column": "name"}).direction is SortDirection.asc
    assert SortKey.parse({"column": "name", "direction": "DESC"}).direction is SortDirection.desc
    typed = SortKey(column="name", direction=SortDirection.desc)
    assert SortKey.parse(typed) is typed


@pytest.mark.parametrize("payload", [{}, "name", {"column": 1}])
def test_sort_key_rejects_a_malformed_key(payload: object) -> None:
    with pytest.raises(BadRequestError, match="malformed sort key"):
        SortKey.parse(payload)


def test_sort_key_rejects_a_bad_direction() -> None:
    with pytest.raises(BadRequestError, match="invalid sort direction"):
        SortKey.parse({"column": "name", "direction": "sideways"})
