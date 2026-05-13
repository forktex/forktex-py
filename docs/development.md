# Development

## Setup

```bash
poetry install --with dev    # editable install + pytest, ruff, pyright, pip-audit, respx
```

## The CI gate

`make ci` is the single command that gates a publish:

```
format-check → lint → license-check → security → test → build
```

It format-checks, lints, verifies dual-license headers across every source file, audits dependencies for known CVEs, runs the test suite, and builds the wheel + sdist with `twine check` — finishing with a *"safe to: make publish-test  /  make publish"* banner. The same chain runs in GitHub Actions on every push and PR across Python 3.14.

```bash
make test        # tests only
make ci          # full publish gate
make publish-test    # upload to TestPyPI
make publish         # upload to PyPI (irreversible per-version)
```

> `make typing` runs pyright standalone but is **not** part of the `ci` chain yet — there are pre-existing cross-SDK type drifts that need to be aligned with the published SDK shapes before it can gate publishes. `make quality` runs `format → lint → typing` for the daily dev loop.

## License headers

Every source file carries the AGPL-3.0 + Commercial dual-license SPDX header, applied idempotently:

```bash
make license-check    # CI gate — fails if any source file is missing the header
make license-fix      # add or refresh headers across src/, tests/, scripts/
make license-strip    # remove headers (used before license-model changes)
```

## Regenerating the Makefile

The `Makefile` is generated from `forktex.json` atoms — never hand-edit it. After changing an atom in the manifest, regenerate:

```bash
forktex fsd makefile sync
```

## Developing against sibling SDK checkouts

Swap the installed `forktex-cloud`, `forktex-intelligence`, and `forktex-network` with editable installs from sibling source trees so SDK edits are picked up without a reinstall:

```bash
make dev-link-sdks                   # editable installs from siblings
export FORKTEX_DEV_SIBLING_SDKS=1    # adds "(dev-linked)" to `forktex --version`
# …iterate on SDK sources…
make dev-unlink-sdks                 # restore pinned PyPI versions
```

`make dev-install` is the one-shot equivalent: editable installs of all three SDKs **and** `forktex-py` itself.

## Installer

The hosted multi-OS installer scripts live under `scripts/install.{sh,ps1}` with shared core logic in `scripts/_install_core.py`. Bundle for hosting:

```bash
make installer-build    # inlines _install_core.py into install.sh + install.ps1, writes dist/install/
make installer-test     # runs the installer across five OS images plus a negative case via Docker
```

`make installer-test` is the cross-distro coverage gate behind the
README-marketed CURL/IWR one-liners (`install.forktex.com/sh`,
`install.forktex.com/ps`). It runs `scripts/install_test.sh` against:

| Image | Path | Expected outcome |
| --- | --- | --- |
| `ubuntu:24.04` | system Python 3.14 via `apt install -t backports` flow | install + `forktex --version` succeeds |
| `fedora:41` | DNF Python 3.14 | install + `forktex --version` succeeds |
| `archlinux:latest` | rolling Python | install + `forktex --version` succeeds |
| `python:3.14-slim` | Debian-slim with stock Python 3.14 | install + `forktex --version` succeeds |
| `python:3.13-slim` | Debian-slim with Python 3.13 (just over the floor) | install + `forktex --version` succeeds |
| `python:3.11-slim` | Debian-slim with Python 3.11 (below the floor) | **must** reject with `rc=2` and "Python ≥ 3.14" message |

The harness uses `FORKTEX_INDEX_URL` to point at TestPyPI so the
test installs whatever's published there. To extend coverage (e.g.
Alpine, Debian-stable, WSL), add an image to
`scripts/install_test.sh` directly — the harness is plain bash by
design (no Python `testcontainers` dependency to keep CI fast).
