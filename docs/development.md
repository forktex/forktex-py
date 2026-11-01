# forktex — Development Reference

Internal documentation for contributors and maintainers. Library consumers do not need this.

---

## Module dependency graph

```
primitives      log · error · types · iso
mechanics       registry
facades         api · cache · database · storage

iso         ← types     (UtcDateTime / UtcDate serialise through iso)
types       ← error     (ErrorEnvelope is a BaseAppModel)
iso         ← log       (canonical UTC timestamp formatting)
─────────────────────────────────────────────────
no facade imports another facade
```

`iso` sits at the bottom, so it raises stdlib `TypeError`/`ValueError` rather than a
`forktex.error` leaf: `error` imports `types` imports `iso`, and a leaf would close the cycle.

Two rules, enforced by `tests/test_architecture/test_layering.py`:

- **A primitive never imports a facade.** The three primitive↔primitive edges above are the only ones.
- **A facade never imports another facade.** Peers compose in the consumer's own service, or
  through a protocol one of them defines and the other satisfies structurally.

---

## Design principles

**One install, no extras.** Every dependency is required. The package root resolves each module on
first attribute access (PEP 562), so `import forktex` exposes all eight without importing any:
`from forktex.iso import to_iso` must not drag in botocore.

**Assertions stripped in production.** Never use `assert` in hot paths or lifecycle methods. Always use explicit `if … raise RuntimeError(…)`.

**Library schemas are isolated.** A library-owned substrate declares its models on a
`substrate_base("<schema>")` of its own, so its tables never enter
`BaseDBModel.metadata` — a consumer's `create_all()` cannot accidentally build them.
`SchemaMigrationRunner` manages such schemas with advisory-lock-protected SQL file
migration. Consumers that cannot create schemas route them to public with
`schema_translate_map={None: "public", "<schema>": "public"}`.

**`schema_translate_map` key for default-schema tables is `None`, not `"public"`.** Tables with `schema=None` (no explicit schema) are remapped by the `None` key. Using `"public"` as the key has no effect on those tables.

**`AppError.details` is `dict[str, object]`, not `JsonObject`.** The envelope stringifies
non-JSON values on the way out; `JsonObject` would reject them on the way in. Narrow the
serializer's return type, never the field's.

**`ContextVar` defaults must be immutable.** A mutable default (e.g. `ContextVar("x", default={})`) creates one shared dict for all coroutines that never set the var — mutations leak across task boundaries. Pattern: `ContextVar("x", default=None)` + factory in getter.

**One name for the process-wide handle: `default()`**, returning `Handle | None`, with
`require_default()` raising instead. `get_engine()`/`get_client()` return the *driver* underneath.
`database` uses `init_engine`/`close_engine` because consumers import it bare; `cache` and
`storage` use `init`/`close` because consumers reach them module-qualified.

**Identifiers are UUIDv7**, declared as the column default so a raw `INSERT` gets the same shape:

```python
id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
```

**Never slice one.** v7 front-loads a millisecond timestamp, so a prefix keeps the clock and
throws away the entropy.

**Tenant isolation is via `namespace`, not a foreign key.** `NamespacedMixin` is the only
tenant-scoping primitive; the library takes no position on what the tenant table is called.

**Internal modules log through `forktex.log.get_logger(__name__)`**, never the bare `logging` API.
forktex never calls `setup_logging()` itself.

---

## Test infrastructure

### Running tests

```bash
# Full suite with the coverage floor (requires Docker for container tests)
make test

# Or pytest directly, without the floor
poetry run python3 -m pytest tests/ -q
```

### Container setup

Session-scoped, one per `pytest` run, defined in `tests/_containers.py` and wired into fixtures in
`tests/conftest.py`:

| Container | Image | Fixture | Tests |
|---|---|---|---|
| Postgres 17 | `postgres:17-alpine` | `postgres_url` / `postgres_url_str` | database, api |
| Redis 7 | `redis:7-alpine` | `redis_url` | cache |
| S3 | `pgsty/silo` (digest-pinned) | `minio_config` | storage |

Per-test isolation is a unique Postgres schema per test, not a container per test.

**A real container is required — there is no in-memory fallback.** These suites exercise JSONB
operators, `FOR UPDATE SKIP LOCKED`, advisory locks, partial/GIN indexes,
`schema_translate_map` and SQLSTATE codes. None of it runs on SQLite.

### Schema isolation in tests

ORM tests map default-schema tables to `fresh_schema`:

```python
engine = create_async_engine(
    url,
    execution_options={
        "schema_translate_map": {
            None: fresh_schema,
        }
    },
)
async with engine.begin() as conn:
    await conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{fresh_schema}"'))
    await conn.run_sync(BaseDBModel.metadata.create_all)
```

Using `"public"` as the key instead of `None` does not remap tables with `schema=None` — those land in the real `public` schema instead of `fresh_schema`, breaking isolation.

### Module-level ORM models in tests

Define ORM models at **module level**, not inside test functions. SQLAlchemy resolves `Mapped[T]` type annotations at class definition time using the module's global namespace. Defining a model inside a function means `Mapped` is not in `__globals__` and annotation resolution fails with `KeyError: 'Mapped'`.

---

## Third-party API notes

### MinIO environment variables

- `MINIO_ROOT_USER` + `MINIO_ROOT_PASSWORD` (not `MINIO_ROOT_SECRET`)
- Without `MINIO_ROOT_PASSWORD` set, the MinIO container exits immediately with no log output

### botocore errors

Match on `exc.response["Error"]["Code"]`, never on `str(exc)`. `_driver_boundary` in
`storage/client.py` wraps anything the driver raises into `StorageError`; a method that needs to
branch on a code catches `ClientError` inside the boundary and re-raises what it does not handle.

### `log.ContextFilter` on a custom handler

See [log.md](log.md#gotchas), and the `capture_json` fixture in `tests/test_log/conftest.py`.

---

## Adding a new module

1. Create `src/forktex/<name>/` with `__init__.py` and `__all__` on every public submodule.
2. Add its dependency to `dependencies` in `pyproject.toml`, and any test-only one to
   `[dependency-groups]`.
3. Add the name to `__all__` in `src/forktex/__init__.py` and to the `TYPE_CHECKING` re-export.
4. Declare it in `LIBRARY` in `tests/test_architecture/test_layering.py` with its level.
5. Add it to `PACKAGES` in `tests/test_architecture/test_public_surface.py` — that list is the
   shipped contract, deliberately explicit rather than derived.
6. Create `docs/<name>.md` with the house sections: Wiring, Public surface, Errors, Gotchas.
7. Create `tests/test_<name>/` and any container fixture it needs in `tests/conftest.py`.

### Module design checklist

- [ ] `__all__` on every public submodule
- [ ] No `assert` — use explicit `if … raise`
- [ ] No mutable `ContextVar` defaults
- [ ] No facade imports another facade (see the dependency graph)
- [ ] Module-level global state documented (if any)

---

## Release process

```bash
# 1. Bump `version` in pyproject.toml and add the CHANGELOG entry.

# 2. The whole gate. `smoke` installs the built wheel into a throwaway venv, so
#    it catches packaging faults the source-tree tests cannot see.
make ci

# 3. Rehearse on TestPyPI, then install from it into a clean venv to confirm.
make publish-test

# 4. Publish. Irreversible per version.
make publish

# 5. Tag.
git tag v0.13.0 && git push --tags
```

---
