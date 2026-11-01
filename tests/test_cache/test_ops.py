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
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from pydantic import BaseModel

from forktex.cache import (
    Cache,
    cached,
    delete,
    deserialize,
    fetch_or_set,
    fetch_swr,
    get,
    init,
    invalidate_key,
    invalidate_prefix,
    key_for,
    serialize,
    set,
    shutdown_background_tasks,
)
from forktex.cache.connection import close
from forktex.cache.errors import InvalidCacheKeyError


@pytest_asyncio.fixture(autouse=True)
async def cache_init(redis_url: str) -> AsyncIterator[None]:
    await init(redis_url)
    yield
    await close()


@pytest.mark.asyncio
async def test_set_and_get() -> None:
    await set("test:k1", "hello", ex=60)
    val = await get("test:k1")
    assert val == "hello"


@pytest.mark.asyncio
async def test_get_miss_returns_none() -> None:
    val = await get("test:nonexistent:" + __name__)
    assert val is None


@pytest.mark.asyncio
async def test_delete() -> None:
    await set("test:k2", "world", ex=60)
    await delete("test:k2")
    val = await get("test:k2")
    assert val is None


@pytest.mark.asyncio
async def test_invalidate_key() -> None:
    await set("test:k3", "data", ex=60)
    await invalidate_key("test:k3")
    assert await get("test:k3") is None


@pytest.mark.asyncio
async def test_invalidate_prefix() -> None:
    await set("prefix:a", "1", ex=60)
    await set("prefix:b", "2", ex=60)
    deleted = await invalidate_prefix("prefix")
    assert deleted >= 2
    assert await get("prefix:a") is None
    assert await get("prefix:b") is None


@pytest.mark.asyncio
async def test_invalidate_prefix_does_not_match_unrelated_keys_sharing_the_string() -> None:
    await set("user:1", "a", ex=60)
    await set("username:foo", "b", ex=60)
    deleted = await invalidate_prefix("user")
    assert deleted == 1
    assert await get("user:1") is None
    assert await get("username:foo") == "b"
    await delete("username:foo")


@pytest.mark.asyncio
async def test_invalidate_prefix_deletes_the_exact_prefix_key_itself() -> None:
    await set("org:abc123", "profile-data", ex=60)
    await set("org:abc123:members", "members-data", ex=60)
    deleted = await invalidate_prefix("org:abc123")
    assert deleted == 2
    assert await get("org:abc123") is None
    assert await get("org:abc123:members") is None


@pytest.mark.asyncio
async def test_fetch_or_set_caches_result() -> None:
    call_count = 0

    async def compute() -> str:
        nonlocal call_count
        call_count += 1
        return "computed"

    key = "test:fos:" + __name__
    result1 = await fetch_or_set(key, 60, compute, (), {}, None)
    result2 = await fetch_or_set(key, 60, compute, (), {}, None)
    assert result1 == "computed"
    assert result2 == "computed"
    assert call_count == 1


@pytest.mark.asyncio
async def test_cached_decorator() -> None:
    call_count = 0

    @cached(ttl=60)
    async def expensive(x: int) -> str:
        nonlocal call_count
        call_count += 1
        return f"result:{x}"

    r1 = await expensive(42)
    r2 = await expensive(42)
    r3 = await expensive(99)
    assert r1 == "result:42"
    assert r2 == "result:42"
    assert r3 == "result:99"
    assert call_count == 2


@pytest.mark.asyncio
async def test_key_for() -> None:
    k = key_for("user", "abc-123")
    assert k == "user:abc-123"
    k2 = key_for("feed")
    assert k2 == "feed"


def test_key_for_none_part_raises_instead_of_collapsing_to_bare_prefix() -> None:
    with pytest.raises(InvalidCacheKeyError):
        key_for("user", None)


@pytest.mark.asyncio
async def test_fetch_swr_returns_fresh_value_on_miss() -> None:
    async def compute() -> str:
        return "fresh"

    key = "test:swr:" + __name__
    result = await fetch_swr(key, ttl=60, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)
    assert result == "fresh"


@pytest.mark.asyncio
async def test_fetch_swr_serves_stale_value_and_refreshes_in_background() -> None:
    call_count = 0

    async def compute() -> str:
        nonlocal call_count
        call_count += 1
        return f"computed-{call_count}"

    key = "test:swr-stale:" + __name__
    first = await fetch_swr(key, ttl=-1, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)
    assert first == "computed-1"

    second = await fetch_swr(key, ttl=-1, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)
    assert second == "computed-1"

    await shutdown_background_tasks()
    assert call_count == 2


@pytest.mark.asyncio
async def test_cached_decorator_stale_ttl_zero_uses_swr_not_fetch_or_set() -> None:
    call_count = 0

    @cached(ttl=0, stale_ttl=0)
    async def compute(x: int) -> str:
        nonlocal call_count
        call_count += 1
        return f"v{call_count}"

    r1 = await compute(1)
    assert r1 == "v1"
    await shutdown_background_tasks()


def test_serialize_deserialize_roundtrip_plain_value() -> None:
    raw = serialize({"a": 1, "b": [1, 2, 3]})
    assert deserialize(raw, None) == {"a": 1, "b": [1, 2, 3]}


@pytest.mark.asyncio
async def test_fetch_swr_keeps_a_valid_entry_when_the_refresh_lock_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def compute() -> str:
        nonlocal calls
        calls += 1
        return f"value-{calls}"

    key = "test:swr-lock-fails:" + __name__
    await delete(key)

    first = await fetch_swr(key, ttl=-1, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)
    assert first == "value-1"
    await shutdown_background_tasks()

    from forktex.cache.cache import Cache

    async def _boom(*_a: object, **_k: object) -> None:
        raise ConnectionError("redis went away mid-lock")

    monkeypatch.setattr(Cache, "_refresh_in_background", _boom)

    second = await fetch_swr(key, ttl=-1, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)

    assert second == "value-1", "a failed refresh must still serve the cached value"
    assert await get(key) is not None, "a failed refresh must not invalidate a valid entry"


def test_default_cache_key_is_insensitive_to_kwarg_order() -> None:
    from forktex.cache.decorators import _default_key

    def fn() -> None: ...

    assert _default_key(fn, (), {"a": 1, "b": 2}) == _default_key(fn, (), {"b": 2, "a": 1})


def test_default_cache_key_ignores_object_identity() -> None:
    from forktex.cache.decorators import _default_key

    def fn() -> None: ...

    class Point:
        def __init__(self, x: int) -> None:
            self.x = x

        def __repr__(self) -> str:
            return f"Point({self.x})"

    assert _default_key(fn, (Point(1),), {}) == _default_key(fn, (Point(1),), {})
    assert _default_key(fn, (Point(1),), {}) != _default_key(fn, (Point(2),), {})


def test_default_cache_key_distinguishes_functions_and_arguments() -> None:
    from forktex.cache.decorators import _default_key

    def one() -> None: ...
    def two() -> None: ...

    assert _default_key(one, (1,), {}) != _default_key(two, (1,), {})
    assert _default_key(one, (1,), {}) != _default_key(one, (2,), {})
    assert _default_key(one, (), {"a": 1}) != _default_key(one, (), {"a": 2})


class _CachedUser(BaseModel):
    id: int
    name: str


def test_serialize_deserialize_roundtrip_pydantic_model() -> None:
    raw = serialize(_CachedUser(id=7, name="ada"))
    assert raw == '{"id":7,"name":"ada"}'

    restored = deserialize(raw, _CachedUser)
    assert isinstance(restored, _CachedUser), "must come back as the model, not a dict"
    assert restored == _CachedUser(id=7, name="ada")


@pytest.mark.asyncio
async def test_cached_decorator_round_trips_a_response_model() -> None:
    calls = 0

    @cached(ttl=60, response_model=_CachedUser)
    async def load_user(user_id: int) -> _CachedUser:
        nonlocal calls
        calls += 1
        return _CachedUser(id=user_id, name="ada")

    await invalidate_prefix("")
    first = await load_user(7)
    second = await load_user(7)

    assert first == second == _CachedUser(id=7, name="ada")
    assert isinstance(second, _CachedUser), "a cache hit must rebuild the model, not return a dict"
    assert calls == 1, "the second call must be served from cache"


@pytest.mark.asyncio
async def test_a_value_is_gone_once_its_ttl_elapses() -> None:
    """Nothing in this suite observed time, so expiry -- the whole point of a
    cache -- was never proven against a real Redis."""
    await set("ttl:probe", "still here", ex=1)
    assert await get("ttl:probe") == "still here"

    await asyncio.sleep(1.2)

    assert await get("ttl:probe") is None


@pytest.mark.asyncio
async def test_a_non_positive_ttl_stores_nothing_instead_of_failing_silently(caplog) -> None:
    """`SET ... EX 0` is rejected by Redis and the error was swallowed, so a
    zero ttl logged an exception on every write and stored nothing anyway."""
    with caplog.at_level("ERROR"):
        await set("ttl:zero", "never stored", ex=0)

    assert await get("ttl:zero") is None
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


@pytest.mark.asyncio
async def test_a_cached_value_has_the_same_type_on_a_hit_as_on_a_miss() -> None:
    """A miss returned the function's own value and a hit returned what came
    back through JSON, so a `datetime` became a `str` on the second call and
    `.isoformat()` crashed on every request after the first."""
    from datetime import datetime

    from forktex import iso

    @cached(ttl=60)
    async def when() -> datetime:
        return iso.now()

    miss = await when()
    hit = await when()

    assert type(miss) is type(hit)
    assert miss == hit


@pytest.mark.asyncio
async def test_a_swr_cached_value_has_the_same_type_on_a_hit_as_on_a_miss() -> None:
    from datetime import datetime

    from forktex import iso

    @cached(ttl=60, stale_ttl=300)
    async def when_swr() -> datetime:
        return iso.now()

    miss = await when_swr()
    hit = await when_swr()
    await shutdown_background_tasks()

    assert type(miss) is type(hit)
    assert miss == hit


@pytest.mark.asyncio
async def test_a_dead_redis_degrades_to_neutral_values_instead_of_raising(caplog) -> None:
    """`docs/cache.md` promises `get`→None, `set`/`delete` no-op and
    `invalidate_prefix`→0 when Redis dies mid-request. Every one of those paths
    was an uncovered `except` block — the documented contract was unproven."""
    handle = Cache("redis://127.0.0.1:1")

    with caplog.at_level("ERROR"):
        assert await handle.get("dead:probe") is None
        await handle.set("dead:probe", "after", ex=60)
        await handle.delete("dead:probe")
        assert await handle.invalidate_prefix("dead") == 0
        assert await handle.invalidate_key("dead:probe") is None

    assert caplog.records, "the degradation is swallowed, so it must at least be logged"
