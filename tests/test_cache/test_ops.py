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

"""Integration tests for forktex.cache — requires Redis container."""

from __future__ import annotations

import pytest
import pytest_asyncio
from pydantic import BaseModel

from forktex.cache import (
    available,
    cached,
    delete,
    deserialize,
    fetch_or_set,
    fetch_swr,
    get,
    get_client,
    init,
    invalidate_key,
    invalidate_prefix,
    key_for,
    serialize,
    set,
    shutdown_background_tasks,
)
from forktex.cache.connection import close
from forktex.cache.errors import CacheInitializationError, CacheNotInitializedError
from forktex.error import AppError


@pytest_asyncio.fixture(autouse=True)
async def cache_init(redis_url: str):
    await init(redis_url)
    yield
    await close()


@pytest.mark.asyncio
async def test_set_and_get():
    await set("test:k1", "hello", ex=60)
    val = await get("test:k1")
    assert val == "hello"


@pytest.mark.asyncio
async def test_get_miss_returns_none():
    val = await get("test:nonexistent:" + __name__)
    assert val is None


@pytest.mark.asyncio
async def test_delete():
    await set("test:k2", "world", ex=60)
    await delete("test:k2")
    val = await get("test:k2")
    assert val is None


@pytest.mark.asyncio
async def test_invalidate_key():
    await set("test:k3", "data", ex=60)
    await invalidate_key("test:k3")
    assert await get("test:k3") is None


@pytest.mark.asyncio
async def test_invalidate_prefix():
    await set("prefix:a", "1", ex=60)
    await set("prefix:b", "2", ex=60)
    deleted = await invalidate_prefix("prefix")
    assert deleted >= 2
    assert await get("prefix:a") is None
    assert await get("prefix:b") is None


@pytest.mark.asyncio
async def test_invalidate_prefix_does_not_match_unrelated_keys_sharing_the_string():
    """ "user" must not match "username:foo" — no bare-string substring match."""
    await set("user:1", "a", ex=60)
    await set("username:foo", "b", ex=60)
    deleted = await invalidate_prefix("user")
    assert deleted == 1
    assert await get("user:1") is None
    assert await get("username:foo") == "b"
    await delete("username:foo")


@pytest.mark.asyncio
async def test_invalidate_prefix_deletes_the_exact_prefix_key_itself():
    await set("org:abc123", "profile-data", ex=60)
    await set("org:abc123:members", "members-data", ex=60)
    deleted = await invalidate_prefix("org:abc123")
    assert deleted == 2
    assert await get("org:abc123") is None
    assert await get("org:abc123:members") is None


@pytest.mark.asyncio
async def test_fetch_or_set_caches_result():
    call_count = 0

    async def compute():
        nonlocal call_count
        call_count += 1
        return "computed"

    key = "test:fos:" + __name__
    result1 = await fetch_or_set(key, 60, compute, (), {}, None)
    result2 = await fetch_or_set(key, 60, compute, (), {}, None)
    assert result1 == "computed"
    assert result2 == "computed"
    assert call_count == 1  # second call hit cache


@pytest.mark.asyncio
async def test_cached_decorator():
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
    assert call_count == 2  # 42 once, 99 once


@pytest.mark.asyncio
async def test_key_for():
    k = key_for("user", "abc-123")
    assert k == "user:abc-123"
    k2 = key_for("feed")
    assert k2 == "feed"


def test_key_for_none_part_raises_instead_of_collapsing_to_bare_prefix():
    """A None part almost always means an unresolved ID upstream — silently
    collapsing onto the bare "user" prefix key would corrupt every other
    caller's per-user cache entries under the same key."""
    with pytest.raises(ValueError):
        key_for("user", None)


@pytest.mark.asyncio
async def test_fetch_swr_returns_fresh_value_on_miss():
    async def compute():
        return "fresh"

    key = "test:swr:" + __name__
    result = await fetch_swr(key, ttl=60, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)
    assert result == "fresh"


@pytest.mark.asyncio
async def test_fetch_swr_serves_stale_value_and_refreshes_in_background():
    call_count = 0

    async def compute():
        nonlocal call_count
        call_count += 1
        return f"computed-{call_count}"

    key = "test:swr-stale:" + __name__
    # ttl=-1 → age (>= 0) is always > ttl, so every read is "stale" and
    # triggers a background refresh, regardless of clock-second rounding.
    first = await fetch_swr(key, ttl=-1, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)
    assert first == "computed-1"

    second = await fetch_swr(key, ttl=-1, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)
    assert second == "computed-1"  # still serves the stale value immediately

    await shutdown_background_tasks()
    assert call_count == 2  # background refresh ran


@pytest.mark.asyncio
async def test_cached_decorator_stale_ttl_zero_uses_swr_not_fetch_or_set():
    """stale_ttl=0 is a degenerate SWR config (refresh on every read), not
    "unset" — it must not silently fall back to plain fetch_or_set."""
    call_count = 0

    @cached(ttl=0, stale_ttl=0)
    async def compute(x: int) -> str:
        nonlocal call_count
        call_count += 1
        return f"v{call_count}"

    r1 = await compute(1)
    assert r1 == "v1"
    await shutdown_background_tasks()


def test_serialize_deserialize_roundtrip_plain_value():
    raw = serialize({"a": 1, "b": [1, 2, 3]})
    assert deserialize(raw, None) == {"a": 1, "b": [1, 2, 3]}


@pytest.mark.asyncio
async def test_available_and_get_client_not_initialized_after_close():
    assert available() is True
    get_client()  # does not raise while initialized

    await close()
    assert available() is False
    # Both bases assert the contract deliberately: `AppError` is what a consumer's
    # error boundary catches, `RuntimeError` is what pre-existing call sites (and
    # `ops._safe_client`) already catch. Losing either is a breaking change.
    with pytest.raises(CacheNotInitializedError) as excinfo:
        get_client()
    assert isinstance(excinfo.value, AppError)
    assert isinstance(excinfo.value, RuntimeError)
    assert await get("test:not-initialized:" + __name__) is None  # ops degrade, don't raise


@pytest.mark.asyncio
async def test_fetch_swr_keeps_a_valid_entry_when_the_refresh_lock_fails(monkeypatch):
    """A Redis blip while *acquiring the background-refresh lock* must not be
    mistaken for a corrupted payload.

    `_refresh_in_background` used to be called inside the same `try` that guards
    payload parsing, and its lock acquisition (`c.set(lock_key, ...)`) is a raw
    client call. So any transient error there was caught, mislogged as "SWR cache
    corrupted", and **deleted a perfectly good key** — then the already-decoded
    value was discarded and `fn` re-ran synchronously. Serving the stale value is
    the entire point of stale-while-revalidate; losing it is the one thing this
    path must not do.
    """
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return f"value-{calls}"

    key = "test:swr-lock-fails:" + __name__
    await delete(key)

    first = await fetch_swr(key, ttl=-1, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)
    assert first == "value-1"
    await shutdown_background_tasks()

    # Break only the refresh path's lock acquisition.
    import forktex.cache.ops as ops

    async def _boom(*_a: object, **_k: object) -> None:
        raise ConnectionError("redis went away mid-lock")

    monkeypatch.setattr(ops, "_refresh_in_background", _boom)

    second = await fetch_swr(key, ttl=-1, stale_ttl=300, fn=compute, args=(), kwargs={}, response_model=None)

    # The cached value must still be served, and the key must survive.
    assert second == "value-1", "a failed refresh must still serve the cached value"
    assert await get(key) is not None, "a failed refresh must not invalidate a valid entry"


def test_default_cache_key_is_insensitive_to_kwarg_order():
    """`f(a=1, b=2)` and `f(b=2, a=1)` are the same call and must share an entry.

    The key was built from `f"...:{kwargs}"`, and a dict's repr preserves
    insertion order — so the two spellings hashed differently and neither ever
    saw the other's cached value. A permanent miss, invisible except as a cache
    that never seems to help.
    """
    from forktex.cache.decorators import _default_key

    def fn() -> None: ...

    assert _default_key(fn, (), {"a": 1, "b": 2}) == _default_key(fn, (), {"b": 2, "a": 1})


def test_default_cache_key_ignores_object_identity():
    """Two equal-valued arguments must produce one key.

    An argument falling back to `object.__repr__` embeds its `id()`, so the entry
    was never re-hit on a later call — and, worse, two *different* objects whose
    reprs happened to match would collide and serve each other's value.
    """
    from forktex.cache.decorators import _default_key

    def fn() -> None: ...

    class Point:
        def __init__(self, x: int) -> None:
            self.x = x

        def __repr__(self) -> str:  # a value-based repr, as a well-behaved type would have
            return f"Point({self.x})"

    assert _default_key(fn, (Point(1),), {}) == _default_key(fn, (Point(1),), {})
    assert _default_key(fn, (Point(1),), {}) != _default_key(fn, (Point(2),), {})


def test_default_cache_key_distinguishes_functions_and_arguments():
    """The key must still separate what genuinely differs."""
    from forktex.cache.decorators import _default_key

    def one() -> None: ...
    def two() -> None: ...

    assert _default_key(one, (1,), {}) != _default_key(two, (1,), {})
    assert _default_key(one, (1,), {}) != _default_key(one, (2,), {})
    assert _default_key(one, (), {"a": 1}) != _default_key(one, (), {"a": 2})


@pytest.mark.asyncio
async def test_failed_init_leaves_the_cache_unavailable(redis_url: str):
    """A failed `init()` must not leave a half-configured client behind.

    `available()` is what `ops._safe_client` trusts to decide whether to talk to
    Redis at all, so a client that never answered `ping()` must not remain set —
    otherwise every subsequent operation tries, fails, and logs, instead of
    degrading quietly.
    """
    await close()
    with pytest.raises(CacheInitializationError) as excinfo:
        await init("redis://127.0.0.1:1/0")  # nothing listens on port 1

    assert isinstance(excinfo.value, AppError)
    assert available() is False, "a failed init must leave the client unset"
    assert await get("test:after-failed-init:" + __name__) is None

    await init(redis_url)  # restore for the rest of the module


class _CachedUser(BaseModel):
    id: int
    name: str


def test_serialize_deserialize_roundtrip_pydantic_model():
    """`@cached(response_model=...)` is this module's headline feature, and both of
    its branches — `serialize(BaseModel)` and `deserialize(..., model)` — were
    never executed: every existing test passed `response_model=None`.
    """
    raw = serialize(_CachedUser(id=7, name="ada"))
    assert raw == '{"id":7,"name":"ada"}'  # model_dump_json, not str(model)

    restored = deserialize(raw, _CachedUser)
    assert isinstance(restored, _CachedUser), "must come back as the model, not a dict"
    assert restored == _CachedUser(id=7, name="ada")


@pytest.mark.asyncio
async def test_cached_decorator_round_trips_a_response_model():
    """End-to-end through Redis: the decorated function's model survives a cache hit."""
    calls = 0

    @cached(ttl=60, response_model=_CachedUser)
    async def load_user(user_id: int) -> _CachedUser:
        nonlocal calls
        calls += 1
        return _CachedUser(id=user_id, name="ada")

    await invalidate_prefix("")  # cold start for this key space
    first = await load_user(7)
    second = await load_user(7)

    assert first == second == _CachedUser(id=7, name="ada")
    assert isinstance(second, _CachedUser), "a cache hit must rebuild the model, not return a dict"
    assert calls == 1, "the second call must be served from cache"
