# forktex.api

A FastAPI factory: trace-id propagation, security headers, CORS, the `AppError` →
`ErrorEnvelope` mapping, and liveness/readiness endpoints, assembled in order.

Both middleware classes are pure ASGI and do not need FastAPI;
`ExceptionEnvelopeMiddleware` lives at `forktex.api.middleware` for an app you assemble yourself.

## Wiring

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

The envelope, trace-id and security-header middleware are already wired. Raise an `AppError`
subclass anywhere and it becomes the right status plus an `ErrorEnvelope` body:

```python
from forktex.error import NotFoundError

@app.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, str]:
    raise NotFoundError(f"project {project_id}")     # → 404 + envelope
```

### Startup and shutdown

Pass your lifespan through `AppConfig`.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from forktex.api import AppConfig, create_app
from forktex.database import close_engine, init_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_engine(settings.db_url)
    yield
    await close_engine()


app = create_app(AppConfig(title="Projects API", lifespan=lifespan))
```

### Readiness probes

`/health` always returns `{"status": "ok"}`. `/health/ready` runs each registered probe and
reports them individually; any failing probe makes the response a **503**.

```python
import sqlalchemy as sa

from forktex.api import AppConfig, create_app
from forktex.database import transactional_session


async def db_ready() -> bool:
    async with transactional_session() as session:
        await session.execute(sa.text("SELECT 1"))
    return True


app = create_app(AppConfig(readiness_probes={"database": db_ready}))
```

A probe that raises and one that returns `False` are both not-ready; the raising one is logged with
a stack trace. Keep probes fast and side-effect-free — they run on every call.

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
| `api_prefix` | `""` | Mounts every route under it, `/docs`, `/redoc`, `/openapi.json` and both health paths included |

### Security headers

Set by `SecurityHeadersMiddleware`, never overwriting one your app already set:

| Header | Value |
|:---|:---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |

CSP and HSTS need per-service values and are not included; add your own middleware.

## Middleware order

Outermost first: **security headers · CORS · trace-id · envelope**.

## Errors

The package raises nothing of its own; it converts
your `AppError`s into responses ([error.md](error.md)). The `AppErrorCode` → status mapping:

| Code | Status | | Code | Status |
|:---|:---|---|:---|:---|
| `not_found` | 404 | | `rate_limited` | 429 |
| `already_exists` | 409 | | `unavailable` | 503 |
| `bad_request` | 400 | | `timeout` | 504 |
| `validation` | 422 | | `cancelled` | 409 |
| `unauthorized` | 401 | | `failed` | 500 |
| `forbidden` | 403 | | `internal` | 500 |
| `conflict` | 409 | | | |

FastAPI's own `HTTPException` and request-validation handling is untouched: a bad query param
still yields FastAPI's standard 422.

## Gotchas

- `AppConfig` rejects unknown fields, so a misspelled setting raises at construction instead of
  being dropped. `api_prefix` must start with `/` and must not end with one.
- `cors_origins=None` means the CORS middleware is **not added at all**, which is not the same as an
  empty allow-list.
- A custom `AppError` subclass whose `code` is outside `AppErrorCode` maps to HTTP 500. See the
  caveat in [error.md](error.md).
- `handle_unexpected=False` re-raises non-`AppError` exceptions for your own handler or the ASGI
  server to deal with. `AppError`s are still enveloped — the switch governs only the catch-all.
- An exception raised *after* the response has started streaming cannot be turned into an envelope
  (the status line is already on the wire), so it is re-raised instead.
- To keep the health routes out of a generated SDK, set `include_in_schema = False` on them.
- `/health/ready` returns 503 **with a body**; read `checks` for which dependency failed.

