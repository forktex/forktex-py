# `forktex.error`

The shared error vocabulary: an `AppError` hierarchy, a stable `AppErrorCode` enum, and the
`ErrorEnvelope` wire shape every ForkTex service returns on failure.

Always bundled — no extra required.

```bash
pip install forktex
```

`AppError` deliberately has **no notion of HTTP**. The status mapping belongs in whatever
transport layer needs one, so a worker, a CLI, or a script can raise and catch the same
errors without importing a web framework.

## Wiring

Shape C — plain classes and functions, no global state.

Raise the typed error from anywhere in your service:

```python
from forktex.error import NotFoundError

async def get_project(session, project_id):
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"project {project_id} not found")
    return project
```

Then let your transport boundary turn it into a response. `to_envelope` builds the wire
shape; you own the code → HTTP-status mapping, because only HTTP needs one:

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

One handler over `AppError` covers every error in the table above, including the ones
`database` raises.

## Public surface

### The hierarchy

`AppError` is the base; catching it covers every error below, including the ones `database` and
other packages raise.

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

> **Caveat that bites.** A status map keyed on `AppErrorCode` — like the one above — has no
> entry for a custom code, so it falls through to **500**. A custom code therefore surfaces
> as an Internal Server Error unless you add it to the map. Either subclass an existing error
> whose code is in the vocabulary (`BadRequestError` for a 400-shaped failure), or extend the
> mapping at your boundary.
>
> The same trap catches services that bridge a *separate* error hierarchy onto this one by string
> matching: `not_found` and `resource_not_found` are different codes, and the mismatch falls through
> to 500. Prefer raising `forktex.error` types directly to translating between vocabularies.

## Errors

This package defines errors rather than raising them. `to_envelope` accepts any `AppError`;
passing something else is a programming error.

## Gotchas

- Migrating from the old `forktex-core` 2.x line: `common.errors.AppError` carried a
  `.status_code` attribute. `error.AppError` does not — HTTP is not its concern. Code
  reading `exc.status_code` gets `None`; map from `exc.code` instead, as shown above.
- `ConflictError` is re-exported by `forktex.database.crud`; it is the same class, so one
  handler catches both import paths.
- The trace id on the envelope comes from `forktex.log`'s contextvar, which is set by
  `TraceIDMiddleware`. Without that middleware the field is empty.
