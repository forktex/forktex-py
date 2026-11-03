# forktex.iso

How a datetime becomes text and back: always UTC, always `datetime.isoformat()`'s default shape. `log`, `types` and `database` all format datetimes through it, so every timestamp the library writes has one shape.

Standard library only.

## Wiring

```python
# times.py
from datetime import date, datetime, timedelta, timezone

from forktex.iso import from_date_iso, from_iso, now, to_date_iso, to_iso

print(now())  # the current time, UTC-aware

print(to_iso(datetime(2026, 1, 1, 12, 0)))  # naive is taken as UTC: 2026-01-01T12:00:00+00:00
print(to_iso(datetime(2026, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=5)))))  # 2026-01-01T07:00:00+00:00

print(from_iso("2026-01-01T12:00:00Z") == from_iso("2026-01-01T12:00:00+00:00"))  # True, both UTC-aware

print(to_date_iso(date(2026, 1, 1)), repr(from_date_iso("2026-01-01")))  # 2026-01-01 datetime.date(2026, 1, 1)
```

## Public surface

`__all__`:

| Name | Behaviour |
| --- | --- |
| `now() -> datetime` | `datetime.now(UTC)` — the canonical "current time" call. |
| `to_iso(value, *, strict=False) -> str` | Naive input is assumed UTC, aware input is converted to UTC, then `isoformat()`. `strict=True` raises `ValueError` on naive input instead. |
| `from_iso(value, *, strict=False) -> datetime` | Parses ISO-8601 and always returns a UTC-aware datetime. `strict=True` raises `ValueError` when the text carries no offset. |
| `to_date_iso(value) -> str` | `YYYY-MM-DD`. A `datetime` is accepted (it subclasses `date`) and its date component used. |
| `from_date_iso(value) -> date` | `date.fromisoformat(value)`. |

## Errors

No custom exception type. Three stdlib ones:

| Raised | When |
| --- | --- |
| `TypeError` | `to_iso()` given something that is not a `datetime`. The message points at `to_date_iso()`. |
| `ValueError` | `to_iso(naive, strict=True)`, or `from_iso(no_offset, strict=True)`. |
| `ValueError` | Malformed text in `from_iso()` / `from_date_iso()`, propagated from stdlib `fromisoformat` — not swallowed, not rewrapped. |

Catch `ValueError` at a parse boundary; there is nothing else to catch.


## Gotchas

- **Naive means UTC by default.** `to_iso`/`from_iso` assume it rather than raising. Pass `strict=True` to refuse a datetime without an offset.
- **`strict` is keyword-only and exists only on `to_iso`/`from_iso`.** The date functions have no strict mode; there is no offset to be ambiguous about.
- **Precision follows `isoformat()`.** Microseconds appear only when nonzero — do not assume a fixed-width string.
- **`to_iso(a_date)` raises.** `date` is not a `datetime`, and passing one is a `TypeError`, not a silent coercion. It is the `to_date_iso()` direction that is lenient: it accepts a full `datetime` and truncates.
- **UTC only.** No display-timezone conversion, no validity predicate, no `timedelta` formatting.
