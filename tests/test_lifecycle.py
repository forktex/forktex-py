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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy as sa

from forktex import cache, database, storage
from forktex.cache import Cache

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

pytestmark = pytest.mark.asyncio

DEAD_POSTGRES = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing"
DEAD_REDIS = "redis://127.0.0.1:1"


@dataclass(frozen=True)
class Facade:
    """One facade's lifecycle, so the shared contract is asserted once per facade
    rather than copied into three files."""

    name: str
    init: Callable[..., Awaitable[None]]
    close: Callable[[], Awaitable[None]]
    default: Callable[[], Any]
    require_default: Callable[[], Any]
    verify: Callable[[], Awaitable[None]]
    not_initialised: type[Exception]
    unreachable: type[Exception]
    live: dict[str, Any]
    dead: dict[str, Any]


@pytest.fixture(params=["database", "cache", "storage"])
def facade(request: pytest.FixtureRequest, postgres_url_str: str, redis_url: str, minio_config: dict) -> Facade:
    match request.param:
        case "database":
            return Facade(
                "database",
                database.init_engine,
                database.close_engine,
                database.default,
                database.require_default,
                database.verify,
                database.DatabaseNotInitializedError,
                database.DatabaseUnreachableError,
                {"db_url": postgres_url_str},
                {"db_url": DEAD_POSTGRES},
            )
        case "cache":
            return Facade(
                "cache",
                cache.init,
                cache.close,
                cache.default,
                cache.require_default,
                cache.verify,
                cache.CacheNotInitializedError,
                cache.CacheUnreachableError,
                {"url": redis_url},
                {"url": DEAD_REDIS},
            )
        case _:
            return Facade(
                "storage",
                storage.init,
                storage.close,
                storage.default,
                storage.require_default,
                storage.verify,
                storage.ClientNotRegisteredError,
                storage.StorageUnreachableError,
                dict(minio_config),
                {**minio_config, "url": "http://127.0.0.1:1"},
            )


async def test_default_reports_absence_and_require_default_raises(facade: Facade) -> None:
    await facade.close()

    assert facade.default() is None
    with pytest.raises(facade.not_initialised):
        facade.require_default()


async def test_init_installs_a_default_that_verify_accepts(facade: Facade) -> None:
    await facade.init(**facade.live)
    try:
        assert facade.default() is facade.require_default()
        await facade.verify()
    finally:
        await facade.close()


async def test_verify_is_the_only_call_that_fails_fast(facade: Facade) -> None:
    """`init` performs no I/O on any facade, so an unreachable backend is
    reported here and nowhere earlier."""
    await facade.init(**facade.dead)
    try:
        assert facade.default() is not None, "init must install the default it was given"
        with pytest.raises(facade.unreachable, match="not reachable"):
            await facade.verify()
    finally:
        await facade.close()


async def test_close_is_idempotent(facade: Facade) -> None:
    await facade.init(**facade.live)
    await facade.close()
    await facade.close()

    assert facade.default() is None


async def test_replacing_the_database_default_disposes_the_old_pool(postgres_url_str: str) -> None:
    await database.init_engine(postgres_url_str)
    first = database.get_engine()
    async with first.connect() as conn:
        await conn.execute(sa.select(sa.literal(1)))
    assert first.pool.checkedin() == 1

    await database.init_engine(postgres_url_str)

    assert database.get_engine() is not first
    assert first.pool.checkedin() == 0, "the replaced engine's pool was not disposed"
    await database.close_engine()


async def test_replacing_the_cache_default_closes_the_old_client(redis_url: str) -> None:
    """Counted server-side: `redis.asyncio` reconnects transparently, so a closed
    client still answers and only Redis can report the released socket."""
    await cache.init(redis_url)
    first = cache.require_default()
    await first.set("lifecycle:probe", "served", ex=60)
    before = await _server_side_clients(first)

    await cache.init(redis_url)
    await cache.require_default().get("lifecycle:probe")

    assert cache.require_default() is not first
    assert await _server_side_clients(cache.require_default()) == before, (
        "replacing the default left the old client's connection open"
    )
    await cache.close()


async def test_replacing_the_storage_default_holds_nothing_to_release(minio_config: dict) -> None:
    """`storage` builds a client per call, so the swap is the whole guarantee."""
    await storage.init(**minio_config)
    first = storage.require_default()

    await storage.init(**minio_config)

    assert storage.require_default() is not first
    await storage.close()


async def _server_side_clients(handle: Cache) -> int:
    listing: str = await handle.client.execute_command("CLIENT", "LIST")
    return listing.count("\n")
