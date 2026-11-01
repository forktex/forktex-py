# forktex.cache

Async Redis cache: connection lifecycle, plain get/set/delete, a `@cached` decorator with
optional stale-while-revalidate, namespaced keys, and Pydantic-aware JSON serialisation.

## Install

```bash
pip install forktex
```

`redis[hiredis]` is a core dependency; the `[cache]` extra declares nothing. The only startup
failure is `init()` being unable to reach Redis.

## Wiring

One Redis client per process, created by `init(url)` and torn down by `close()`. `Cache(url)` is
the same handle built directly; the module-level functions are shims over one default instance.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

import forktex.cache as cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    await cache.init(settings.redis_url)
    yield
    await cache.shutdown_background_tasks()
    await cache.close()


app = FastAPI(lifespan=lifespan)
```

The default is **per-process**: a worker must call `init()` in its own startup hook. Without it the
helpers degrade to no-ops rather than raising, so a missing worker-side `init()` is silent.

`shutdown_background_tasks()` awaits in-flight stale-while-revalidate refreshes; call it before
`close()`.

## Public surface

```python
from forktex.cache import (
    CachePrefix,
    available,
    cached,
    close,
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
```

| Name | Description |
|---|---|
| `init(url)` | Async. Create the client from a Redis URL and `PING` it. |
| `close()` | Async. Close the client and clear the global. Idempotent. |
| `available()` | `True` if the client global is set. |
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

`cached` signature:

```python
@cached(
    ttl=300,                      # seconds; with stale_ttl set, the refresh threshold instead
    stale_ttl=None,               # set → stale-while-revalidate
    key_builder=None,             # callable(*args, **kwargs) -> str
    response_model=None,          # pydantic model for deserialisation
)
async def get_org(org_id: str) -> OrgResponse: ...
```

Namespaced keys:

```python
from enum import StrEnum

from forktex.cache import invalidate_prefix, key_for


class Prefix(StrEnum):
    ORG = "org"


await invalidate_prefix(key_for(Prefix.ORG, org_id))
```

## Errors

| Raised | When | Catch? |
|---|---|---|
| `CacheInitializationError` | `init()` — `PING` failed. The client is reset to `None` first, so `available()` keeps reporting `False`. | At startup only. Let it stop the process unless the cache is genuinely optional. |
| `CacheNotInitializedError` | `get_client()` before `init()`. | A wiring bug; do not catch. |
| `ValueError` | `key_for(prefix, ...)` with a `None` part. | A wiring bug; do not catch. |

Both derive from `CacheError`, which subclasses `AppError` ([error.md](error.md)) and
`RuntimeError`.

Every read and write catches Redis exceptions, logs them and returns a neutral value, so no
`try/except` is needed around ordinary cache use. The URL is masked in logs.

## Gotchas

- **Failures are swallowed.** Without `init()`, or if Redis dies mid-request, `get` returns `None`,
  `set`/`delete` no-op and `invalidate_prefix` returns `0` — a misconfigured cache looks like a 100%
  miss rate. Check `available()` at startup.
- **`invalidate_prefix("")` scans every key** in the database and deletes all of them. Non-empty
  prefixes match on the `:` delimiter, so `invalidate_prefix("user")` hits `"user"` and `"user:123"`
  but never `"username:foo"`.
- **`key_for` rejects `None` parts**, which would collapse a per-entity key onto the shared
  `prefix` key. Empty-string parts *are* dropped.
- **`stale_ttl=0` still selects SWR.** Only `stale_ttl=None` picks plain `fetch_or_set`; `0` is a
  valid TTL and refreshes on every read.
- **The default key builder SHA-256s `f"{module}.{name}:{args}:{kwargs}"`**, so arguments need a
  stable `repr`. Pass `key_builder` for anything non-trivial.
- **SWR refresh is Redis-locked** under `lock:<key>` for 10 s, so one process refreshes at a time.
  The refresh itself is a bare `asyncio.Task`: call `shutdown_background_tasks()` before `close()`.
- **`set` requires `ex`** — there is no way to write a key without a TTL through this module.
- **`cache.set` shadows the builtin** when imported bare; prefer `import forktex.cache as cache`.
