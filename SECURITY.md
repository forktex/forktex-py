# Security Policy

## Reporting a vulnerability

Email **info@forktex.com** with details and, where possible, a reproduction. Please do
not open a public issue for an unfixed vulnerability.

## Supported versions

| Version | Supported |
| --- | --- |
| 1.0.x | ✅ |

## Scope

`forktex` is a library. It has no CLI, no daemon, no network listener and no
filesystem access of its own; it runs inside the consuming service's process,
under that service's privileges. The security-relevant surface:

- **`database`**: SQL construction. Every statement is a SQLAlchemy construct;
  nothing builds SQL by interpolating a value. Identifiers that reach DDL are
  validated (`database.identifiers`) and quoted. Client-supplied filters only
  reach the columns listed in `ColumnSource(allowed=...)`.
- **`storage`**: presigned URLs and upload forms grant access without other
  credentials until they expire; choose `expires_in`, `content_type` and
  `max_size_bytes` accordingly. `public_access="bucket-policy"` makes a bucket
  world-readable.
- **`api`**: an inbound `X-Request-ID` is accepted only if it matches
  `^[A-Za-z0-9._-]{1,128}$`, so a client cannot inject lines into the logs.
  Error envelopes never carry driver text.
- **`storage`, `cache`, `database`** connect to infrastructure you configure.
  Credentials are passed in by you and held in memory only.

## What this library does not do

- **No phone-home.** The only network traffic is to the infrastructure you
  configure.
- **No authentication or authorization.** These are the consuming service's
  concern.
- **No log redaction.** `log` emits the fields you give it; do not put
  credentials, tokens or personal data into log context.

## Operator responsibilities

- **Transport security.** Use TLS-enabled URLs for every backing service.
- **Dependency currency.** `make audit` runs `pip-audit` against the resolved
  environment and is part of `make ci`.

## Licensing

Dual-licensed: AGPL-3.0-or-later, or a commercial license from FORKTEX S.R.L. See
[LICENSE](LICENSE) and [NOTICE](NOTICE).
