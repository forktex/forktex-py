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


import uuid
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from math import ceil
from typing import Any

from pydantic import AliasChoices, Field
from sqlalchemy import ColumnElement, Select, SQLColumnExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from forktex.database.errors import InvalidKeysetError
from forktex.database.integrity import integrity_boundary
from forktex.database.pagination import Page, decode_cursor, encode_cursor, keyset_predicate
from forktex.error import BadRequestError


class PageResponse[T](Page[T]):
    items: list[T] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items", "data"),
        serialization_alias="data",
    )
    total: int | None = Field(
        default=None,
        validation_alias=AliasChoices("total", "total_count", "totalCount"),
        serialization_alias="totalCount",
    )
    limit: int
    current_page: int | None = None
    total_pages: int | None = None

    @property
    def data(self) -> list[T]:
        return self.items

    @property
    def total_count(self) -> int | None:
        return self.total

    def apply_to_page_data[U](self, map_func: Callable[[T], U]) -> PageResponse[U]:
        return PageResponse[U](
            items=[map_func(item) for item in self.items],
            has_more=self.has_more,
            limit=self.limit,
            total=self.total,
            current_page=self.current_page,
            total_pages=self.total_pages,
        )


class ScrollResponse[T](Page[T]):
    items: list[T] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items", "data"),
        serialization_alias="data",
    )
    limit: int

    @property
    def data(self) -> list[T]:
        return self.items

    def apply_to_scroll_data[U](self, map_func: Callable[[T], U]) -> ScrollResponse[U]:
        return ScrollResponse[U](
            items=[map_func(item) for item in self.items],
            limit=self.limit,
            has_more=self.has_more,
            next_cursor=self.next_cursor,
        )


async def get[T](
    session: AsyncSession,
    model: type[T],
    value: object,
    *,
    key: str = "id",
    options: list | None = None,
) -> T | None:
    if not hasattr(model, key):
        raise BadRequestError(f"unknown column {key!r} on {model.__name__}")

    stmt = select(model).where(getattr(model, key) == value)
    if options:
        stmt = stmt.options(*options)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def find_one_by[T](
    session: AsyncSession,
    model: type[T],
    **filters: object,
) -> T | None:
    stmt = select(model).filter_by(**filters)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_all[T](
    session: AsyncSession,
    model: type[T],
    *,
    options: list | None = None,
) -> list[T]:
    stmt = select(model)
    if options:
        stmt = stmt.options(*options)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create[T](
    session: AsyncSession,
    model: type[T],
    **values: object,
) -> T:
    obj = model(**values)
    session.add(obj)
    async with integrity_boundary():
        await session.flush()
    await session.refresh(obj)
    return obj


_DEFAULT_PAGE_SIZE = 100


async def paginate[T](
    session: AsyncSession,
    model: type[T],
    page: int = 1,
    page_size: int = 100,
    conditions: list[ColumnElement] | None = None,
    order_by: list[ColumnElement] | None = None,
    joins: list[InstrumentedAttribute] | None = None,
    options: list | None = None,
) -> PageResponse[T]:
    stmt = select(model)

    if options:
        stmt = stmt.options(*options)
    if joins:
        for join in joins:
            stmt = stmt.outerjoin(join)
    if conditions:
        stmt = stmt.where(*conditions)
    if order_by:
        stmt = stmt.order_by(*order_by)

    return await _paginate_query(session, stmt, page, page_size)


async def paginate_scroll[T](
    session: AsyncSession,
    model: type[T],
    limit: int = 20,
    conditions: list[ColumnElement] | None = None,
    order_by: list[ColumnElement] | None = None,
    joins: list[InstrumentedAttribute] | None = None,
    options: list | None = None,
    *,
    keyset: list[ColumnElement] | None = None,
    cursor: str | None = None,
    ascending: bool = True,
) -> ScrollResponse[T]:
    if cursor is not None and not keyset:
        raise InvalidKeysetError("a cursor needs the keyset it was built from")
    if keyset and order_by:
        raise InvalidKeysetError("the keyset is the ordering; pass one or the other, not both")
    stmt = select(model)

    if options:
        stmt = stmt.options(*options)
    if joins:
        for join in joins:
            stmt = stmt.outerjoin(join)
    if conditions:
        stmt = stmt.where(*conditions)
    if keyset and cursor is not None:
        stmt = stmt.where(keyset_predicate(_resume_after(keyset, cursor), ascending=ascending))
    if order_by:
        stmt = stmt.order_by(*order_by)
    elif keyset:
        stmt = stmt.order_by(*(expr.asc() if ascending else expr.desc() for expr in keyset))

    return await _paginate_scroll_query(session, stmt, limit, keyset=keyset)


async def _paginate_query[T](
    session: AsyncSession,
    query: Select[tuple[T]] | Select[Any],
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> PageResponse[T]:
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = _DEFAULT_PAGE_SIZE

    total_count_stmt = select(func.count()).select_from(query.subquery())
    total_count = (await session.execute(total_count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    paginated_stmt = query.offset(offset).limit(page_size)
    result = await session.execute(paginated_stmt)
    data = list(result.scalars().all())

    has_more = (page * page_size) < total_count
    total_pages = ceil(total_count / page_size)

    return PageResponse(
        items=data,
        has_more=has_more,
        limit=page_size,
        total=total_count,
        current_page=page,
        total_pages=total_pages,
    )


async def _paginate_scroll_query[T](
    session: AsyncSession,
    query: Select[tuple[T]] | Select[Any],
    limit: int = 20,
    *,
    keyset: list[ColumnElement] | None = None,
) -> ScrollResponse[T]:
    if limit < 1:
        limit = 20

    scroll_stmt = query.limit(limit + 1)
    result = await session.execute(scroll_stmt)
    data = list(result.scalars().all())

    has_more = len(data) > limit
    if has_more:
        data = data[:limit]

    next_cursor: str | None = None
    if has_more and keyset:
        boundary = [_value_of(data[-1], expr) for expr in keyset]
        if boundary[-1] is None:
            raise InvalidKeysetError(
                "the last keyset level is the tiebreaker and must not be NULL — "
                "end the keyset on a non-nullable column such as the primary key"
            )
        next_cursor = encode_cursor(boundary)

    return ScrollResponse(
        items=data,
        has_more=has_more,
        limit=limit,
        next_cursor=next_cursor,
    )


def _resume_after(keyset: list[ColumnElement], cursor: str) -> list[tuple[SQLColumnExpression[Any], Any]]:
    boundary = decode_cursor(cursor, expected_length=len(keyset))
    return [(expr, _typed_cursor_value(expr, value)) for expr, value in zip(keyset, boundary, strict=True)]


def _parse_cursor_text(python_type: type, text: str) -> object:
    if python_type is datetime:
        return datetime.fromisoformat(text)
    if python_type is date:
        return date.fromisoformat(text)
    if python_type is uuid.UUID:
        return uuid.UUID(text)
    if python_type is Decimal:
        return Decimal(text)
    return text


def _typed_cursor_value(expr: ColumnElement, value: object) -> object:
    python_type = _python_type(expr)
    if python_type is None or not isinstance(value, str):
        return value
    try:
        return _parse_cursor_text(python_type, value)
    except ValueError, ArithmeticError:
        raise BadRequestError("invalid cursor") from None


def _python_type(expr: ColumnElement) -> type | None:
    try:
        return expr.type.python_type
    except NotImplementedError:
        return None


def _value_of(row: object, expr: ColumnElement) -> object:
    key = getattr(expr, "key", None) or getattr(expr, "name", None)
    if key is None or not hasattr(row, str(key)):
        raise BadRequestError("keyset ordering must use mapped columns so a cursor can be built")
    return getattr(row, str(key))


__all__ = [
    "PageResponse",
    "ScrollResponse",
    "create",
    "find_one_by",
    "get",
    "list_all",
    "paginate",
    "paginate_scroll",
]
