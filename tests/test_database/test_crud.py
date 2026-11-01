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

from typing import Any
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from forktex.database.crud import _typed_cursor_value
from forktex.database import (
    BaseDBModel,
    PageResponse,
    ScrollResponse,
    TimestampMixin,
    create,
    find_one_by,
    get,
    list_all,
    paginate,
    paginate_scroll,
)
from forktex.database.errors import InvalidKeysetError
from forktex.error import BadRequestError


class _CrudItem(BaseDBModel, TimestampMixin):
    __tablename__ = "crud_item_test"
    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    score: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


@pytest.mark.asyncio
async def test_create_and_get(models_session: AsyncSession) -> None:
    item = await create(models_session, _CrudItem, name="alpha", score=10)
    await models_session.commit()
    fetched = await get(models_session, _CrudItem, item.id)
    assert fetched is not None
    assert fetched.name == "alpha"
    assert fetched.score == 10


@pytest.mark.asyncio
async def test_get_missing_returns_none(models_session: AsyncSession) -> None:
    result = await get(models_session, _CrudItem, uuid.uuid7())
    assert result is None


@pytest.mark.asyncio
async def test_get_an_unknown_key_is_a_named_bad_request_not_an_attribute_error(
    models_session: AsyncSession,
) -> None:
    """A bare AttributeError here reached a client as an opaque 500; `filters`
    already answered the same condition with BadRequestError."""
    with pytest.raises(BadRequestError, match="unknown column 'bogus_column'"):
        await get(models_session, _CrudItem, "x", key="bogus_column")


@pytest.mark.asyncio
async def test_find_one_by(models_session: AsyncSession) -> None:
    await create(models_session, _CrudItem, name="beta", score=20)
    await models_session.commit()
    found = await find_one_by(models_session, _CrudItem, name="beta")
    assert found is not None
    assert found.score == 20


@pytest.mark.asyncio
async def test_find_one_by_no_match(models_session: AsyncSession) -> None:
    result = await find_one_by(models_session, _CrudItem, name="nonexistent-xyz")
    assert result is None


@pytest.mark.asyncio
async def test_duplicate_name_raises_already_exists(models_session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    from forktex.error import AlreadyExistsError

    await create(models_session, _CrudItem, name="gamma")
    await models_session.commit()
    with pytest.raises(AlreadyExistsError) as exc_info:
        await create(models_session, _CrudItem, name="gamma")

    assert exc_info.value.code == "already_exists"
    assert "gamma" not in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, IntegrityError)


@pytest.mark.asyncio
async def test_list_all(models_session: AsyncSession) -> None:
    created = {f"list-{i}-{uuid.uuid7().hex}" for i in range(3)}
    for name in created:
        await create(models_session, _CrudItem, name=name)
    await models_session.commit()
    items = await list_all(models_session, _CrudItem)
    assert created <= {item.name for item in items}


@pytest.mark.asyncio
async def test_paginate_splits_correctly(models_session: AsyncSession) -> None:
    suffix = uuid.uuid7().hex
    for i in range(5):
        await create(models_session, _CrudItem, name=f"page-{i}-{suffix}", score=i)
    await models_session.commit()

    conditions = [_CrudItem.name.like(f"page-%-{suffix}")]
    p1: PageResponse = await paginate(models_session, _CrudItem, page=1, page_size=3, conditions=conditions)
    p2: PageResponse = await paginate(models_session, _CrudItem, page=2, page_size=3, conditions=conditions)

    assert len(p1.data) == 3
    assert p1.has_more is True
    assert p1.total_count == 5
    assert p1.total_pages == 2
    assert len(p2.data) == 2
    assert p2.has_more is False


@pytest.mark.asyncio
async def test_paginate_scroll_has_more(models_session: AsyncSession) -> None:
    suffix = uuid.uuid7().hex
    for i in range(4):
        await create(models_session, _CrudItem, name=f"scroll-{i}-{suffix}")
    await models_session.commit()

    conditions = [_CrudItem.name.like(f"scroll-%-{suffix}")]
    result: ScrollResponse = await paginate_scroll(models_session, _CrudItem, limit=2, conditions=conditions)
    assert len(result.data) == 2
    assert result.has_more is True


@pytest.mark.asyncio
async def test_paginate_scroll_no_more_when_exhausted(models_session: AsyncSession) -> None:
    suffix = uuid.uuid7().hex
    for i in range(2):
        await create(models_session, _CrudItem, name=f"exhaust-{i}-{suffix}")
    await models_session.commit()

    conditions = [_CrudItem.name.like(f"exhaust-%-{suffix}")]
    result: ScrollResponse = await paginate_scroll(models_session, _CrudItem, limit=10, conditions=conditions)
    assert len(result.data) == 2
    assert result.has_more is False


@pytest.mark.asyncio
async def test_paginate_clamps_invalid_page_and_page_size(models_session: AsyncSession) -> None:
    suffix = uuid.uuid7().hex
    for i in range(3):
        await create(models_session, _CrudItem, name=f"clamp-{i}-{suffix}")
    await models_session.commit()

    conditions = [_CrudItem.name.like(f"clamp-%-{suffix}")]
    result: PageResponse = await paginate(models_session, _CrudItem, page=0, page_size=0, conditions=conditions)
    assert result.current_page == 1
    assert result.limit == 100, "an unusable page_size clamps to the declared default, not a second magic number"
    assert len(result.data) == 3


@pytest.mark.asyncio
async def test_paginate_scroll_clamps_invalid_limit(models_session: AsyncSession) -> None:
    suffix = uuid.uuid7().hex
    for i in range(3):
        await create(models_session, _CrudItem, name=f"scroll-clamp-{i}-{suffix}")
    await models_session.commit()

    conditions = [_CrudItem.name.like(f"scroll-clamp-%-{suffix}")]
    result: ScrollResponse = await paginate_scroll(models_session, _CrudItem, limit=0, conditions=conditions)
    assert result.limit == 20
    assert len(result.data) == 3


@pytest.mark.asyncio
async def test_paginate_scroll_can_actually_advance_past_page_one(models_session: AsyncSession) -> None:
    suffix = uuid.uuid7().hex
    for i in range(5):
        await create(models_session, _CrudItem, name=f"seek-{i}-{suffix}", score=i)
    await models_session.commit()

    conditions = [_CrudItem.name.like(f"seek-%-{suffix}")]
    keyset = [_CrudItem.name, _CrudItem.id]

    p1 = await paginate_scroll(
        models_session,
        _CrudItem,
        limit=2,
        conditions=conditions,
        keyset=keyset,
    )
    assert [i.name for i in p1.data] == [f"seek-0-{suffix}", f"seek-1-{suffix}"]
    assert p1.has_more is True
    assert p1.next_cursor is not None

    p2 = await paginate_scroll(
        models_session,
        _CrudItem,
        limit=2,
        conditions=conditions,
        keyset=keyset,
        cursor=p1.next_cursor,
    )
    assert [i.name for i in p2.data] == [f"seek-2-{suffix}", f"seek-3-{suffix}"]

    p3 = await paginate_scroll(
        models_session,
        _CrudItem,
        limit=2,
        conditions=conditions,
        keyset=keyset,
        cursor=p2.next_cursor,
    )
    assert [i.name for i in p3.data] == [f"seek-4-{suffix}"]
    assert p3.has_more is False
    assert p3.next_cursor is None

    seen = [i.name for i in (*p1.data, *p2.data, *p3.data)]
    assert seen == sorted(seen)
    assert len(set(seen)) == 5


@pytest.mark.asyncio
async def test_paginate_scroll_without_keyset_still_returns_a_first_page(
    models_session: AsyncSession,
) -> None:
    suffix = uuid.uuid7().hex
    for i in range(3):
        await create(models_session, _CrudItem, name=f"nokeyset-{i}-{suffix}")
    await models_session.commit()

    result = await paginate_scroll(
        models_session,
        _CrudItem,
        limit=2,
        conditions=[_CrudItem.name.like(f"nokeyset-%-{suffix}")],
    )
    assert len(result.data) == 2
    assert result.has_more is True
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_paginate_scroll_newest_first_over_a_timestamp_and_uuid_keyset(models_session: AsyncSession) -> None:
    suffix = uuid.uuid7().hex
    for i in range(5):
        await create(models_session, _CrudItem, name=f"recent-{i}-{suffix}")
        await models_session.commit()

    seen: list[str] = []
    cursor = None
    while True:
        page = await paginate_scroll(
            models_session,
            _CrudItem,
            limit=2,
            conditions=[_CrudItem.name.like(f"recent-%-{suffix}")],
            keyset=[_CrudItem.created_at, _CrudItem.id],
            cursor=cursor,
            ascending=False,
        )
        seen += [item.name for item in page.items]
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert seen == [f"recent-{i}-{suffix}" for i in reversed(range(5))]


@pytest.mark.asyncio
async def test_paginate_scroll_refuses_a_cursor_without_its_keyset(models_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="keyset"):
        await paginate_scroll(models_session, _CrudItem, cursor="WyJ4Il0=")


class _NullableItem(BaseDBModel):
    __tablename__ = "crud_nullable_item_test"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    rank: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("ascending", [True, False])
async def test_keyset_pagination_crosses_nulls_in_both_directions(
    models_session: AsyncSession, ascending: bool
) -> None:
    ranks = {1: None, 2: None, 3: 30, 4: 20, 5: 10, 6: None}
    models_session.add_all(_NullableItem(id=i, rank=r) for i, r in ranks.items())
    await models_session.flush()

    keyset = [_NullableItem.rank, _NullableItem.id]
    seen: list[int] = []
    cursor = None
    for _ in range(len(ranks)):
        page = await paginate_scroll(
            models_session,
            _NullableItem,
            limit=2,
            keyset=keyset,
            cursor=cursor,
            ascending=ascending,
        )
        seen += [item.id for item in page.items]
        if not page.has_more:
            break
        cursor = page.next_cursor

    expected = [5, 4, 3, 1, 2, 6] if ascending else [6, 2, 1, 3, 4, 5]
    assert seen == expected


@pytest.mark.parametrize(
    ("column_type", "bad"),
    [
        (sa.Numeric, "garbage"),
        (sa.DateTime, "not-a-date"),
        (sa.Uuid, "not-a-uuid"),
    ],
)
def test_a_tampered_cursor_value_is_a_bad_request_for_every_parsed_type(
    column_type: type[sa.types.TypeEngine[Any]], bad: str
) -> None:
    with pytest.raises(BadRequestError, match="invalid cursor"):
        _typed_cursor_value(sa.Column("sort_key", column_type), bad)


@pytest.mark.asyncio
async def test_paginate_scroll_refuses_a_keyset_and_an_order_by_together(models_session: AsyncSession) -> None:
    """`order_by` won while the WHERE clause resumed on the keyset boundary, so a
    disagreeing pair silently returned a page that skipped or repeated rows."""
    with pytest.raises(InvalidKeysetError, match="one or the other"):
        await paginate_scroll(
            models_session,
            _CrudItem,
            limit=2,
            keyset=[_CrudItem.id],
            order_by=[_CrudItem.score.desc()],
        )


@pytest.mark.asyncio
async def test_a_nullable_tiebreaker_is_refused_rather_than_minting_a_cursor_it_rejects(
    models_session: AsyncSession,
) -> None:
    """The last keyset level is the tiebreaker, and ascending order cannot
    express "after NULL". `paginate_scroll` minted such a cursor anyway and then
    answered the next request with `BadRequestError("invalid cursor")` — a 400 on
    a cursor the API itself had handed out."""
    models_session.add_all(_NullableItem(id=i, rank=None) for i in (1, 2, 3))
    await models_session.flush()

    with pytest.raises(InvalidKeysetError, match="tiebreaker"):
        await paginate_scroll(models_session, _NullableItem, limit=2, keyset=[_NullableItem.rank])
