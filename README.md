<p align="center">
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/v/forktex.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/pyversions/forktex.svg" alt="Python"></a>
  <a href="https://github.com/forktex/forktex-py/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/forktex.svg" alt="License"></a>
</p>

<p align="center"><em>The shared Python substrate for ForkTex services.</em></p>

Logging, errors, typed models, PostgreSQL, Redis, S3 and a FastAPI app factory.
Use one module or all of them: each works on its own, and importing one does
not load the others.

```bash
pip install forktex
```

Python 3.14. One install, no extras.

## Modules

| | Module | What you get | Needs |
|---|---|---|---|
| **Basics** | [`log`](docs/log.md) | Structured JSON logs, with a trace id that follows each request, job and thread | — |
| | [`error`](docs/error.md) | One error hierarchy with stable codes, and the JSON envelope clients receive | — |
| | [`types`](docs/types.md) | Pydantic base models: camelCase on the wire, frozen value objects, UTC datetimes | — |
| | [`iso`](docs/iso.md) | Datetimes to and from text, always in UTC | — |
| **Infrastructure** | [`database`](docs/database.md) | Transactions, ORM models, CRUD, pagination, safe client filters, advisory locks, SQL migrations | PostgreSQL |
| | [`cache`](docs/cache.md) | `get`/`set`, a `@cached` decorator with stale-while-revalidate, key invalidation | Redis |
| | [`storage`](docs/storage.md) | Upload, download, presigned download and upload links, browser upload forms | Any S3-compatible server |
| **App factory** | [`api`](docs/api.md) | A FastAPI app with error envelopes, trace ids, security headers, CORS and health checks | FastAPI (included) |

Every module page starts with a complete example you can copy and run, then
lists the module's functions, its errors and the things to know.

## Where to start

| You want to | Read |
|---|---|
| Use one module | Its page, linked above |
| Build a web service, adding modules as you need them | [The guide](docs/guide.md): an app first, then a database, a cache, file uploads |
| Run something outside a web app (a worker, a script) | The module's page: every module except `api` works without FastAPI |

## Stability

From 1.0.0, semantic versioning covers every name in each module's `__all__`.
Anything else is internal and may change in any release. Changes are listed in
the [CHANGELOG](CHANGELOG.md).

## Contributing

Working on `forktex` itself? Start with
[`docs/development.md`](docs/development.md).

## Licence

AGPL-3.0-or-later, or a commercial licence from FORKTEX S.R.L.
(info@forktex.com). See [LICENSE](LICENSE) and [NOTICE](NOTICE).
