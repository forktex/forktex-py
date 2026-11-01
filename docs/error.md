# `forktex.error`

The shared error vocabulary: an `AppError` hierarchy, a stable `AppErrorCode` enum, and the
`ErrorEnvelope` wire shape every ForkTex service returns on failure.

`AppError` carries no HTTP status; the mapping lives at the transport edge.

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

`to_envelope` builds the wire shape. `forktex.api.create_app` already maps the code to a status
([api.md](api.md#errors) has the table); for a transport you assemble yourself:

```python
envelope = to_envelope(exc, trace_id=get_trace_id())
body = envelope.model_dump(mode="json")
```

`mode="json"` matters: `details` is coerced with a `str` fallback only in JSON mode, so a UUID or
datetime in there fails to serialise otherwise.

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
- The envelope's trace id comes from `forktex.log`'s contextvar, set by `TraceIDMiddleware`.
  Without that middleware the field is empty.
