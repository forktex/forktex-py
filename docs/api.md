# forktex.api

A preconfigured FastAPI factory: trace-id propagation, security headers, CORS, the
`AppError` → `ErrorEnvelope` mapping, and liveness/readiness endpoints — assembled in the right
order, then handed back for you to extend.

## Install

```bash
pip install "forktex[api]"
```

The extra declares `fastapi`. Importing the package needs nothing: only `create_app` touches
FastAPI, and it raises an `ImportError` naming the extra if it is missing.

```
ImportError: Install 'forktex[api]' (fastapi) to use forktex.api
```

Both middleware classes are **pure ASGI**, so `from forktex.api import SecurityHeadersMiddleware`
works with no FastAPI installed and can be applied to any ASGI app.
`ExceptionEnvelopeMiddleware` is not re-exported from the package root — `create_app` wires it
for you; reach it at `forktex.api.middleware` if you are assembling an app yourself.

## Wiring

**Shape C — consumer-owned object, no global state.** You own the app; there is no registry, no
`init()`, no singleton.

```python
from forktex.api import AppConfig, create_app

app = create_app(
    AppConfig(
        title="Projects API",
        version="1.4.0",
        cors_origins=["https://app.example.com"],
    )
)

app.include_router(projects_router)
```

That is a complete, correctly layered app. You do **not** need to add the envelope middleware, the
trace-id middleware, or the security headers yourself.

Raise an `AppError` subclass anywhere and it becomes the right status plus an `ErrorEnvelope` body:

```python
from forktex.error import NotFoundError

@app.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, str]:
    raise NotFoundError(f"project {project_id}")     # → 404 + envelope
```

### Startup and shutdown

Pass your lifespan through `AppConfig`; there is no need to assign `app.router.lifespan_context`
afterwards.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from forktex.api import AppConfig, create_app
from forktex.database import close_engine, init_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine(settings.db_url)
    yield
    await close_engine()


app = create_app(AppConfig(title="Projects API", lifespan=lifespan))
```

### Readiness probes

`/health` is liveness and always returns `{"status": "ok"}`. `/health/ready` runs each probe you
register and reports them individually, so you extend the built-in endpoint rather than hiding it
and mounting your own. Any failing probe makes the whole response a **503**.

```python
import sqlalchemy as sa

from forktex.api import AppConfig, create_app
from forktex.database import get_session


async def db_ready() -> bool:
    async with get_session() as session:
        await session.execute(sa.text("SELECT 1"))
    return True


app = create_app(AppConfig(readiness_probes={"database": db_ready}))
```

A probe that raises and a probe that returns `False` are both reported as not-ready; the raising one
is logged with a stack trace, so the two stay distinguishable. Keep probes fast (≤200 ms) and
side-effect-free — they run on every call.

## Public surface

| Name | Purpose |
|:---|:---|
| `create_app(config)` | Build the configured FastAPI instance |
| `AppConfig` | The configuration model — every switch below |
| `HealthProbe` | The readiness-probe callable type (`() -> Awaitable[bool]`) |
| `LivenessResponse` / `ReadinessResponse` | Response models for the health endpoints |
| `SecurityHeadersMiddleware` | Pure-ASGI defensive response headers |

### `AppConfig`

| Field | Default | Effect |
|:---|:---|:---|
| `title` / `version` / `description` | `"ForkTex Service"` / `"1.0.0"` / `""` | Passed to FastAPI and OpenAPI |
| `debug` | `False` | FastAPI debug mode |
| `lifespan` | `None` | Your startup/shutdown context manager |
| `enable_trace_id` | `True` | Wire `forktex.log.TraceIDMiddleware` |
| `enable_security_headers` | `True` | Wire `SecurityHeadersMiddleware` |
| `enable_exception_handler` | `True` | `AppError` → `ErrorEnvelope` |
| `handle_unexpected` | `True` | Also map uncaught `Exception` to a generic 500 envelope |
| `cors_origins` | `None` | `None` leaves CORS off entirely |
| `cors_allow_credentials` / `_methods` / `_headers` | `True` / `["*"]` / `["*"]` | CORS detail |
| `readiness_probes` | `{}` | Name → async predicate, run by `/health/ready` |
| `readiness_timeout` | `5.0` | Per-probe seconds before a probe counts as not-ready |

### Security headers

`SecurityHeadersMiddleware` sets four conservative headers, and never overwrites one your app
already set:

| Header | Value |
|:---|:---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |

CSP and HSTS are deliberately **not** included: both need per-service values, and a wrong default
either breaks the app or provides false assurance. Add your own middleware for those.

## Middleware order

`add_middleware` applies in reverse, so the assembled stack is, outermost first:

**security headers · CORS · trace-id · envelope**

The envelope sits *inside* trace-id so the contextvar is still live when the error body is built —
which is what makes the response `traceId`, the `X-Request-ID` header, and the log records agree.
This ordering is load-bearing: `TraceIDMiddleware` binds the id with a context manager that resets
it on exit, so an envelope built anywhere outside it would carry a null `traceId`. Security headers
are outermost so they stamp every response, errors and CORS preflights included.

## Errors

The package raises nothing of its own beyond the `ImportError` for a missing extra — it converts
your `AppError`s into responses. See [error.md](error.md) for the hierarchy.

The `AppErrorCode` → status mapping:

| Code | Status | | Code | Status |
|:---|:---|---|:---|:---|
| `not_found` | 404 | | `rate_limited` | 429 |
| `already_exists` | 409 | | `unavailable` | 503 |
| `bad_request` | 400 | | `timeout` | 504 |
| `validation` | 422 | | `cancelled` | 409 |
| `unauthorized` | 401 | | `failed` | 500 |
| `forbidden` | 403 | | `internal` | 500 |
| `conflict` | 409 | | | |

FastAPI's own `HTTPException` and request-validation handling runs closer to the route and is left
untouched — a bad query param still yields FastAPI's standard 422.

## Gotchas

- `cors_origins=None` means the CORS middleware is **not added at all**, which is not the same as an
  empty allow-list.
- A custom `AppError` subclass whose `code` is outside `AppErrorCode` maps to HTTP 500. See the
  caveat in [error.md](error.md).
- `handle_unexpected=False` re-raises non-`AppError` exceptions for your own handler or the ASGI
  server to deal with. `AppError`s are still enveloped — the switch governs only the catch-all.
- An exception raised *after* the response has started streaming cannot be turned into an envelope
  (the status line is already on the wire), so it is re-raised instead.
- The health routes are registered on the app. To keep them out of a generated SDK, set
  `include_in_schema = False` on them rather than removing them.
- `/health/ready` returns 503 with a body — it is a real report, not an empty error. Read `checks`
  to see which dependency failed.

## Running background work in the same app

See [worker.md](worker.md#running-a-worker-inside-a-fastapi-app) for consuming a queue inside
this app's lifespan, the one-trace-id-across-both-tiers contract, and when to split the two
into separate processes instead.
