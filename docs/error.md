# `forktex.error`

The shared error vocabulary: an `AppError` hierarchy, a stable `AppErrorCode` enum, and the
`ErrorEnvelope` wire shape every ForkTex service returns on failure.

`AppError` carries no HTTP status; the mapping lives at the transport edge.

## Wiring

```python
# errors.py
from forktex.error import AppError, BadRequestError, NotFoundError, to_envelope


def find_invoice(invoice_id: str) -> dict[str, str]:
    if not invoice_id.startswith("INV-"):
        raise BadRequestError("invoice ids start with INV-", details={"invoice_id": invoice_id})
    raise NotFoundError(f"invoice {invoice_id} not found")


for invoice_id in ("INV-2", "7"):
    try:
        find_invoice(invoice_id)
    except AppError as error:  # one handler covers every forktex error, and your own
        print(error.code, to_envelope(error, trace_id="req-1").model_dump(mode="json"))
```

```
not_found {'code': 'not_found', 'message': 'invoice INV-2 not found', 'details': {}, 'traceId': 'req-1'}
bad_request {'code': 'bad_request', 'message': 'invoice ids start with INV-', 'details': {'invoice_id': '7'}, 'traceId': 'req-1'}
```

`forktex.api.create_app` does this for every request, and maps each code to an
HTTP status ([api.md](api.md#errors) has the table). For a transport you
assemble yourself, build the body with `to_envelope(error, trace_id=get_trace_id())`
and `.model_dump(mode="json")`: `details` is turned into JSON, with `str` as the
fallback, only in JSON mode.

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
# custom_error.py
from forktex.error import AppError, ConflictError


class InsufficientCreditError(AppError):  # its own code; an HTTP edge maps it to 500 unless you extend the map
    code = "insufficient_credit"


class SeatLimitReachedError(ConflictError):  # keeps the "conflict" code, so it maps to 409
    pass


print(InsufficientCreditError("not enough credit").code, SeatLimitReachedError("no seats left").code)
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
- **`details` accepts any value and serialises it with a `str` fallback**, so a `UUID` or
  `datetime` you put in reaches the client as a string. Put the shape you want on the wire.
