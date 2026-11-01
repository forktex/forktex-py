# `forktex.error`

The shared error vocabulary: an `AppError` hierarchy, a stable `AppErrorCode` enum, and the
`ErrorEnvelope` wire shape every ForkTex service returns on failure.

## Install

```bash
pip install forktex
```

No extra required.

`AppError` has **no notion of HTTP**: the status mapping belongs in the transport layer, so a
worker, a CLI or a script raises and catches the same errors without a web framework.

## Wiring

Raise the typed error from anywhere in your service:

```python
from forktex.error import NotFoundError

async def get_project(session, project_id):
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"project {project_id} not found")
    return project
```

`to_envelope` builds the wire shape; you own the code → HTTP-status mapping:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forktex.error import AppError, AppErrorCode, to_envelope

_STATUS = {
    AppErrorCode.NOT_FOUND: 404,
    AppErrorCode.ALREADY_EXISTS: 409,
    AppErrorCode.CONFLICT: 409,
    AppErrorCode.BAD_REQUEST: 400,
    AppErrorCode.VALIDATION: 422,
    AppErrorCode.UNAUTHORIZED: 401,
    AppErrorCode.FORBIDDEN: 403,
    AppErrorCode.RATE_LIMITED: 429,
    AppErrorCode.UNAVAILABLE: 503,
}

app = FastAPI()


@app.exception_handler(AppError)
async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS.get(exc.code, 500),
        content=to_envelope(exc).model_dump(by_alias=True),
    )
```

## Public surface

### The hierarchy

`AppError` is the base. One handler over it covers every error below, including those raised by
`database` and the other packages.

| Class | Code | HTTP |
|:---|:---|:---|
| `BadRequestError` | `bad_request` | 400 |
| `UnauthorizedError` | `unauthorized` | 401 |
| `ForbiddenError` | `forbidden` | 403 |
| `NotFoundError` | `not_found` | 404 |
| `ConflictError` | `conflict` | 409 |
| `AlreadyExistsError` | `already_exists` | 409 |
| `UnprocessableEntityError` | `validation` | 422 |
| `TooManyRequestsError` | `rate_limited` | 429 |
| `ServiceUnavailableError` | `unavailable` | 503 |

### `AppErrorCode`

The stable published vocabulary: `not_found`, `already_exists`, `bad_request`, `validation`,
`unauthorized`, `forbidden`, `conflict`, `rate_limited`, `unavailable`, `timeout`, `cancelled`,
`failed`, `internal`.

### `ErrorEnvelope` and `to_envelope`

`ErrorEnvelope` is the response body: an error code, a human-readable message, and an optional
trace id. `to_envelope(error)` builds one from any `AppError`.

## Extending with your own codes

`AppError.code` is an open `str`, not a closed enum, so a service can raise a domain-specific code
and keep the envelope:

```python
from forktex.error import AppError


class InsufficientCreditError(AppError):
    code = "insufficient_credit"
```

> **A custom code falls through to 500**, because a status map keyed on `AppErrorCode` has no entry
> for it. Either subclass an error whose code is already in the vocabulary, or extend the map at
> your boundary. The same applies to bridging another hierarchy by string matching: `not_found` and
> `resource_not_found` are different codes.

## Errors

This package defines errors rather than raising them.

## Gotchas

- **`AppError` carries no `.status_code`** — map from `exc.code`.
- `ConflictError` is re-exported by `forktex.database.crud`; it is the same class, so one handler
  catches both import paths.
- The envelope's trace id comes from `forktex.log`'s contextvar, set by `TraceIDMiddleware`.
  Without that middleware the field is empty.
