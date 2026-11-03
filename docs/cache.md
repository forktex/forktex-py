# forktex.cache

Async Redis cache: connection lifecycle, plain get/set/delete, a `@cached` decorator with
optional stale-while-revalidate, namespaced keys, and Pydantic-aware JSON serialisation.

## Wiring

```bash
export REDIS_URL=redis://localhost:6379/0
```

```python
# rates.py
import asyncio
import os
from enum import StrEnum

from pydantic import BaseModel

import forktex.cache as cache


class Prefix(StrEnum):
    RATE = "rate"


class Rate(BaseModel):
    currency: str
    value: float


@cache.cached(ttl=60, response_model=Rate, key_builder=lambda currency: cache.key_for(Prefix.RATE, currency))
async def rate(currency: str) -> Rate:
    print("fetching", currency)  # an expensive call; runs once per minute per currency
    return Rate(currency=currency, value=1.08)


async def main() -> None:
    await cache.init(os.environ["REDIS_URL"])  # performs no I/O
    await cache.verify()  # PING, so a bad URL fails here rather than on first use

    print(await rate("EUR"))  # fetching EUR, then the value
    print(await rate("EUR"))  # from Redis
    await cache.set("greeting", "hello", ex=30)
    print(await cache.get("greeting"))

    await cache.invalidate_prefix(Prefix.RATE)  # drops "rate" and every "rate:*" key
    print(await cache.get(cache.key_for(Prefix.RATE, "EUR")))  # None

    await cache.shutdown_background_tasks()
    await cache.close()


asyncio.run(main())
```

In a web app, call `init()` in the lifespan and `close()` on the way out, after
`shutdown_background_tasks()`, which waits for in-flight stale-while-revalidate
refreshes.

The default is **per-process**: a worker calls `init()` in its own startup.
Without it every helper silently does nothing (see Gotchas), so call `verify()`
at startup, or wire it into `create_app`'s `readiness_probes`.

`Cache(url)` is the same handle built directly; the module-level functions use
the process-wide one.

## Public surface

| Name | Description |
|---|---|
| `init(url)` | Async. Install the process-wide client for a Redis URL, closing any it replaces. No I/O. |
| `close()` | Async. Close the client and clear the global. Idempotent. |
| `available()` | `True` once `init()` has run. It does not check that Redis is reachable; `verify()` does. |
| `default()` | The process-wide `Cache`, or `None` before `init()`. |
| `require_default()` | The same, raising `CacheNotInitializedError` instead of returning `None`. |
| `verify()` | Async. `PING`. Raises `CacheUnreachableError`. |
| `get_client()` | The raw `redis.asyncio.Redis`. Raises if `init()` has not run. |
| `get(key)` | Async. Value or `None`. |
| `set(key, value, ex)` | Async. Write with a TTL in seconds. |
| `delete(key)` | Async. Delete one key. |
| `invalidate_key(key)` | Async. Alias for `delete`. |
| `invalidate_prefix(prefix)` | Async. Delete `prefix` and every `prefix:*` key; returns the count. |
| `cached(...)` | Decorator for async functions — see below. |
| `fetch_or_set(key, ttl, fn, args, kwargs, response_model)` | Async. Cache-aside primitive behind `@cached`. |
| `fetch_swr(key, ttl, stale_ttl, fn, args, kwargs, response_model)` | Async. Stale-while-revalidate primitive. |
| `shutdown_background_tasks()` | Async. Await outstanding SWR refresh tasks. |
| `key_for(prefix, *parts)` | Build `"prefix:part1:part2"`. |
| `CachePrefix` | Empty `StrEnum` base — consumers subclass it with their own prefixes. |
| `serialize(value)` | JSON string; `BaseModel` uses `model_dump_json()`, everything else `json.dumps(default=str)`. |
| `deserialize(data, model)` | Parse JSON; validates into `model` when one is given. |

### `@cached(*, ttl=60, stale_ttl=None, key_builder=None, response_model=None)`

| Option | Effect |
|---|---|
| `ttl` | Seconds a value is kept. With `stale_ttl`, the age after which a read refreshes it in the background. |
| `stale_ttl` | Turns on stale-while-revalidate: a value older than `ttl` is still served for this many seconds while one process refreshes it. |
| `key_builder` | `(*args, **kwargs) -> str`. Use it with `key_for` so `invalidate_prefix` can find the keys. |
| `response_model` | A pydantic model the cached JSON is validated into. |

## Errors

| Raised | When | Catch? |
|---|---|---|
| `CacheUnreachableError` | `verify()` — `PING` failed. | At startup only, if you call `verify()`. |
| `CacheNotInitializedError` | `get_client()` before `init()`. | A wiring bug; do not catch. |
| `InvalidCacheKeyError` | `key_for()` given a `None` part, which would collapse a per-entity key onto the shared prefix. | A wiring bug; do not catch. |

All three derive from `CacheError`, which subclasses `AppError` ([error.md](error.md)) and
`RuntimeError`.

## Gotchas

- **`@cached` returns the JSON round-trip of your value, on a miss as well as a hit.** A cache can
  only store JSON, so a `datetime` comes back as a string and a `tuple` as a list — on every call,
  not just the cached ones. Pass `response_model=` to get a model back; for anything else, cache
  the serialisable shape and convert at the call site.

- **Failures are swallowed.** Without `init()`, or if Redis dies mid-request, `get` returns `None`,
  `set`/`delete` no-op and `invalidate_prefix` returns `0` — a misconfigured cache looks like a 100%
  miss rate. Call `verify()` at startup.
- **`invalidate_prefix("")` scans every key** in the database and deletes all of them. Non-empty
  prefixes match on the `:` delimiter, so `invalidate_prefix("user")` hits `"user"` and `"user:123"`
  but never `"username:foo"`.
- **`key_for` rejects `None` parts**, which would collapse a per-entity key onto the shared
  `prefix` key. Empty-string parts *are* dropped.
- **A non-positive `ttl` or `stale_ttl` stores nothing**, so every read refetches. `stale_ttl=0`
  still selects SWR — only `stale_ttl=None` picks plain `fetch_or_set`.
- **The default key builder SHA-256s the qualified name, the args and the sorted kwargs**, so arguments need a
  stable `repr`. Pass `key_builder` for anything non-trivial.
- **SWR refresh is Redis-locked** under `lock:<key>` for 10 s, so one process refreshes at a time.
  The refresh itself is a bare `asyncio.Task`: call `shutdown_background_tasks()` before `close()`.
- **`set` requires `ex`** — there is no way to write a key without a TTL through this module.
- **`cache.set` shadows the builtin** when imported bare; prefer `import forktex.cache as cache`.
