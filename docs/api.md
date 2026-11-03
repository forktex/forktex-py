# forktex.api

A FastAPI factory: trace-id propagation, security headers, CORS, the `AppError` →
`ErrorEnvelope` mapping, and liveness/readiness endpoints, assembled in order.

## Wiring

```python
# service.py
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

import forktex.database as database
from forktex.api import AppConfig, create_app
from forktex.error import NotFoundError
from forktex.log import setup_logging

projects = APIRouter(prefix="/projects")


@projects.get("/{project_id}")
async def get_project(project_id: str) -> dict[str, str]:
    raise NotFoundError(f"project {project_id} not found")  # 404 with an error envelope


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(service="projects")
    await database.init_engine(os.environ["DATABASE_URL"])
    yield
    await database.close_engine()


async def database_ready() -> bool:
    await database.verify()  # raises when the database cannot be reached: not ready
    return True


app = create_app(
    AppConfig(
        title="Projects API",
        version="1.4.0",
        lifespan=lifespan,
        cors_origins=["https://app.example.com"],
        readiness_probes={"database": database_ready},
    )
)
app.include_router(projects)
```

```bash
uvicorn service:app
curl -i localhost:8000/projects/7
# HTTP/1.1 404 Not Found … x-request-id: 01a1… x-content-type-options: nosniff …
# {"code": "not_found", "message": "project 7 not found", "details": {}, "traceId": "01a1…"}
curl localhost:8000/health/ready
# {"status":"ready","checks":{"database":true}}
```

- Raise an `AppError` subclass anywhere: it becomes its status and an
  `ErrorEnvelope` body. Any other exception becomes a generic 500 envelope.
- `/health` always answers `{"status": "ok"}`. `/health/ready` runs every probe
  and answers 503, naming each failing check, if any probe returns `False`,
  raises, or exceeds `readiness_timeout`. Probes run on every call, so keep them
  fast and free of side effects.
- Both middleware classes are plain ASGI. `ExceptionEnvelopeMiddleware` is in
  `forktex.api.middleware` for an app you assemble yourself.

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

