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

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from forktex.database.errors import InvalidAdvisoryKeyError
from forktex.database.locks import advisory_key, advisory_lock, key_from_uuid, try_advisory_lock
from tests.conftest import sessions_for

LOCK_KEY = advisory_key("test", "advisory", "lock")


@pytest.mark.asyncio
async def test_advisory_lock_serialises_access(postgres_url_str: str) -> None:
    engine = create_async_engine(postgres_url_str)
    order: list[str] = []
    shared_key = LOCK_KEY

    async def worker(name: str) -> None:
        async with advisory_lock(engine, shared_key):
            order.append(f"{name}:enter")
            await asyncio.sleep(0.05)
            order.append(f"{name}:exit")

    await asyncio.gather(worker("A"), worker("B"))

    a_enter, a_exit = order.index("A:enter"), order.index("A:exit")
    b_enter, b_exit = order.index("B:enter"), order.index("B:exit")
    assert a_exit < b_enter or b_exit < a_enter, f"Lock did not serialise: {order}"
    await engine.dispose()


@pytest.mark.asyncio
async def test_try_advisory_lock_non_blocking_acquires(postgres_url_str: str) -> None:
    engine = create_async_engine(postgres_url_str)
    key = advisory_key("test", "try", "free")

    async with try_advisory_lock(engine, key) as acquired:
        assert acquired is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_try_advisory_lock_contention_second_caller_gets_false(postgres_url_str: str) -> None:
    engine = create_async_engine(postgres_url_str)
    key = advisory_key("test", "try", "contended")
    holder_ready = asyncio.Event()
    release_holder = asyncio.Event()
    second_acquired: list[bool] = []

    async def holder() -> None:
        async with try_advisory_lock(engine, key) as acquired:
            assert acquired is True
            holder_ready.set()
            await release_holder.wait()

    async def contender() -> None:
        await holder_ready.wait()
        async with try_advisory_lock(engine, key) as acquired:
            second_acquired.append(acquired)
        release_holder.set()

    await asyncio.gather(holder(), contender())
    assert second_acquired == [False]
    await engine.dispose()


@pytest.mark.asyncio
async def test_advisory_lock_released_after_context(postgres_url_str: str) -> None:
    """Under a timeout: an unreleased lock makes the second acquire block forever,
    which hangs the run instead of failing it."""
    engine = create_async_engine(postgres_url_str)
    key = advisory_key("test", "release")

    async def acquire_twice() -> None:
        async with advisory_lock(engine, key):
            pass
        async with advisory_lock(engine, key):
            pass

    try:
        await asyncio.wait_for(acquire_twice(), timeout=5)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_advisory_lock_different_keys_do_not_block(postgres_url_str: str) -> None:
    engine = create_async_engine(postgres_url_str)
    both_inside = asyncio.Barrier(2)

    async def hold(key: int) -> None:
        async with advisory_lock(engine, key):
            await asyncio.wait_for(both_inside.wait(), timeout=5)

    try:
        await asyncio.gather(hold(advisory_key("lock", "a")), hold(advisory_key("lock", "b")))
    finally:
        await engine.dispose()


def test_advisory_key_is_deterministic_and_fits_signed_bigint() -> None:

    a = advisory_key("myapp", "migrations")
    assert a == advisory_key("myapp", "migrations")
    assert -(2**63) <= a < 2**63


def test_advisory_key_parts_cannot_collide_by_concatenation() -> None:

    assert advisory_key("a", "b") != advisory_key("ab")
    assert advisory_key("a_b") != advisory_key("a", "b")


def test_advisory_key_requires_a_part() -> None:

    with pytest.raises(InvalidAdvisoryKeyError, match="at least one part"):
        advisory_key()


def test_key_from_uuid_folds_128_bits_into_signed_64() -> None:
    import uuid as _uuid

    u = _uuid.UUID("12345678-1234-5678-1234-567812345678")
    k = key_from_uuid(u)
    assert k == key_from_uuid(u)
    assert -(2**63) <= k < 2**63
    assert key_from_uuid(_uuid.uuid7()) != key_from_uuid(_uuid.uuid7())


def test_key_from_uuid_rejects_non_uuid() -> None:
    with pytest.raises(InvalidAdvisoryKeyError):
        key_from_uuid("not-a-uuid")


@pytest.mark.asyncio
async def test_xact_lock_is_released_at_transaction_end(postgres_url_str: str) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from forktex.database.locks import xact_lock

    key = advisory_key("test", "xact", uuid.uuid7().hex)
    engine = create_async_engine(postgres_url_str)
    maker = sessions_for(engine)
    try:
        async with maker() as s1:
            async with s1.begin():
                await xact_lock(s1, key)
                async with maker() as s2:
                    held = (await s2.execute(sa.select(sa.func.pg_try_advisory_lock(key)))).scalar_one()
                    assert held is False
            async with maker() as s3:
                free = (await s3.execute(sa.select(sa.func.pg_try_advisory_lock(key)))).scalar_one()
                assert free is True
                await s3.execute(sa.select(sa.func.pg_advisory_unlock(key)))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_advisory_lock_is_released_when_the_body_aborts_its_transaction(postgres_url_str: str) -> None:
    engine = create_async_engine(postgres_url_str, pool_size=1, max_overflow=0)
    key = key_from_uuid(uuid.uuid7())
    try:
        with pytest.raises(sa.exc.DBAPIError):
            async with advisory_lock(engine, key) as conn:
                await conn.execute(sa.text("SELECT 1/0"))

        other = create_async_engine(postgres_url_str)
        try:
            async with try_advisory_lock(other, key) as acquired:
                assert acquired
        finally:
            await other.dispose()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_advisory_lock_rolls_back_work_left_uncommitted_on_its_connection(postgres_url_str: str) -> None:
    engine = create_async_engine(postgres_url_str)
    table = f"lock_uncommitted_{uuid.uuid7().hex}"
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f'CREATE TABLE "{table}" (n int)'))
        async with advisory_lock(engine, advisory_key(table)) as conn:
            await conn.execute(sa.text(f'INSERT INTO "{table}" VALUES (1)'))
        async with engine.connect() as conn:
            assert (await conn.execute(sa.text(f'SELECT count(*) FROM "{table}"'))).scalar_one() == 0
    finally:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f'DROP TABLE IF EXISTS "{table}"'))
        await engine.dispose()


class _UnreleasableConnection:
    def __init__(self) -> None:
        self.invalidated = False

    async def rollback(self) -> None:
        raise ConnectionError("server closed the connection")

    async def invalidate(self) -> None:
        self.invalidated = True


@pytest.mark.asyncio
async def test_a_lock_that_cannot_be_released_closes_its_connection() -> None:
    from forktex.database.locks import _release

    conn = _UnreleasableConnection()
    await _release(conn, 1)
    assert conn.invalidated
