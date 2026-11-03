# Developing `forktex`

For working on the library itself. Everything a consumer needs is in the
[README](../README.md) and the module pages; nothing here is part of the public
contract.

## Architecture

```
basics          iso · types · error · log
internal        registry (named clients, used by storage)
infrastructure  database · cache · storage
app factory     api

types → iso     UtcDateTime / UtcDate serialise through iso
error → types   ErrorEnvelope is a BaseAppModel
log   → iso     timestamps
api   → error, log, and the infrastructure modules only through probes you pass in
```

- **A basic module never imports an infrastructure module**, and the three edges
  above are the only ones between basics.
- **Infrastructure modules never import each other.** They are peers over
  different services; a consumer composes them. `database` may use `error`,
  `types`, `log` and `iso`.
- **`iso` raises stdlib `TypeError` / `ValueError`**, not `forktex.error`
  classes: `error` imports `types`, which imports `iso`, so it would be a cycle.
- **The package root resolves modules lazily** (PEP 562), so `import forktex`
  exposes all eight and `from forktex.iso import now` loads neither SQLAlchemy
  nor Redis. Every dependency is required; there are no extras.

**One process-wide default per infrastructure module.** `default()` returns the
handle or `None`; `require_default()` raises instead. `init` performs no I/O and
releases what it replaced; `verify()` is the explicit probe. `database` names
its pair `init_engine` / `close_engine` because consumers import it bare;
`cache` and `storage` use `init` / `close` because consumers use them
module-qualified. Each handle class (`Database`, `Cache`, `StorageClient`) works
without the default, so a process can hold several.

**Transactions.** `transaction()` and `@transaction` own the boundary: the
session they hand out refuses `commit`, `rollback` and `begin`
(`_ManagedSession`), and the commit itself runs inside `integrity_boundary()`,
so a constraint that fails at commit becomes the same typed error as one that
fails at flush. `session()` hands the boundary to the caller and raises if ORM
writes are left uncommitted.

**Errors.** Every module keeps its errors in its own `errors.py`, all deriving
from `forktex.error.AppError` with a `code` from `AppErrorCode` and no HTTP
status. The code-to-status map lives only in `forktex.api`. Driver text never
reaches an error message; the original is the `__cause__`.

**Migrations.** `SchemaMigrationRunner` applies `v{NNNN}__name.sql` files, each
in one transaction with its version row, under an advisory lock. The version
table's `checksum` column is nullable and is added to a version table that
lacks it; rows recorded without a checksum are not verified.

**Logging.** Library modules log through `forktex.log.get_logger(__name__)` and
never call `setup_logging()`. `forktex` attaches a `NullHandler` to its own
logger at import. Context lives in `ContextVar`s with immutable defaults.

## Layout

```
src/forktex/
  __init__.py        lazy module resolution
  registry.py        ClientRegistry: named, per-process clients (internal)
  iso/ types/ error/ log/
  database/ cache/ storage/
  api/
tests/               one test_<module>/ per module, plus test_package.py and test_lifecycle.py
docs/                one consumer page per module, and this file
```

## Commands

```bash
make install   # poetry install --with dev
make test      # pytest with the coverage floor; needs Docker
make ci        # lock, format, lint, licence headers, types, audit, tests, build, wheel smoke
```

Run `make ci` on its own, since a concurrent run races over `dist/`.

Tests run against real PostgreSQL, Redis and an S3-compatible server through
testcontainers (`tests/_containers.py`, fixtures in `tests/conftest.py`). Each
database test gets a schema of its own. Define ORM models in tests at module
level: SQLAlchemy resolves `Mapped[...]` against the module's globals.

## Conventions

- Python 3.14 only; PEP 695 generics and PEP 758 `except A, B:` are in use.
- Every module declares `__all__`, and it is the public contract.
- `src/` has no lint exemptions. A new `Any` in a signature is a prompt to name
  the type.
- Ids are UUIDv7 (`uuid.uuid7()`), set as the column `default=`, and never
  sliced.
- Errors come from a module's `errors.py` or `forktex.error`; never a bare
  builtin, and no `assert` outside tests.
- Tests exercise the public API against real services and would pass against
  the installed wheel.
- The consumer docs describe the library as it is. Every snippet in them is a
  complete file that runs as written. History lives in git and the CHANGELOG.
- `forktex_flow`, `forktex_grid` and `forktex_log.*` appear as string literals:
  they are schema names and context keys in deployed systems. Do not rename
  them.

## Adding a module

1. Create `src/forktex/<name>/` with `__init__.py`, `__all__` and `errors.py`.
2. Add its dependencies to `pyproject.toml`.
3. Add it to `__all__` and the `TYPE_CHECKING` imports in
   `src/forktex/__init__.py`, and to `MODULES` in `tests/test_package.py`.
4. Write `docs/<name>.md`: Wiring (a complete, runnable file), Public surface,
   Errors, Gotchas. Link it from the README.
5. Create `tests/test_<name>/`, with any container fixture in
   `tests/conftest.py`.

## Release

Publishing is manual.

1. Bump `version` in `pyproject.toml` and add a dated CHANGELOG section, one line
   per change.
2. Run `make ci`. It builds `dist/` and installs the wheel into a clean venv.
3. Run `make publish-test` and try the TestPyPI install, then `make publish`. A
   version can never be uploaded twice.
4. Tag it: `git tag vX.Y.Z`.
