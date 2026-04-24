# Changelog

All notable changes to the `forktex` CLI are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Per-facet credential verbs** — each of `cloud` / `intelligence` / `network` exposes the identical `login` and `logout` subcommands with the same option set (`--endpoint`, `--email`, `--password`, `--api-key`, `--global`, `--new-account`). Built via a shared `build_facet_commands()` factory so the three facets stay literally symmetric.
- **`forktex status`** (top-level) — aggregate credential-state table across all three facets. Supports `--json` for scripting and `--no-probe` for offline use.
- **`forktex intelligence status`** — operational status command (API health + whoami), matching the shape of `cloud status` and `network status`.
- **`forktex network`** — new facet group, wired to the `forktex-network` SDK (pinned `>=1.0.0,<2.0.0`). Commands: `login`, `logout`, `status`.
- **Intelligence verbs grouped under the facet** — `forktex intelligence {ask, run, scrape, index-ecosystem, status, login, logout}` so the three facets sit at the same level in the CLI tree.
- **Root loop** — bare `forktex` prints per-facet cards driven by live auth state; auto-upgrades into the intelligence chat REPL when intelligence is reachable. Interactive chat has no dedicated verb — it *is* the bare invocation. `AgentDriver` Protocol in `forktex.agent.root_loop.driver` reserved for a future local-model driver shipped from the Intelligence SDK.
- **`make dev-link-sdks` / `make dev-unlink-sdks`** — editable installs of the three sibling SDK repos (`../cloud/sdk-py`, `../intelligence/sdk-py`, `../network/sdk-py`) for ecosystem development against in-tree sources. `FORKTEX_DEV_SIBLING_SDKS=1` appends `(dev-linked)` to `forktex --version` as a courtesy signal.

### Changed — breaking

- **`forktex cloud login`** — pre-existing verb, now one of three identical `<facet> login` commands.
- **`forktex intelligence init`** removed. Use `forktex intelligence login` — preserves the register-or-login + `create_api_key` flow that lived inside `init`.
- **Top-level `chat` / `ask` / `run` / `scrape`** removed. `chat` is now just bare `forktex`; the others live under `forktex intelligence`.
- **Top-level `init`** (interactive wizard orchestrating intelligence + cloud) removed; run the per-facet `login` commands directly.
- **`forktex auth` group** removed in favour of per-facet verbs.

### Migration

```bash
# Before                                   # After
forktex cloud login --api-key ftx-…        forktex cloud login --api-key ftx-…       (unchanged)
forktex intelligence init --global         forktex intelligence login --global
forktex auth status                        forktex status
forktex auth set <facet>                   forktex <facet> login
forktex auth clear <facet>                 forktex <facet> logout
forktex chat                               forktex                                    (bare)
forktex ask "…"                            forktex intelligence ask "…"
forktex run "…"                            forktex intelligence run "…"
forktex scrape https://…                   forktex intelligence scrape https://…
```

On-disk credential files are unchanged (`~/.forktex/{cloud,intelligence,network}.json`). Nothing to migrate for existing users.

## [1.0.0] — 2026-04-24

V1 release. Classifier flipped to `Production/Stable`. SemVer contract guaranteed from this point: breaking changes require a new major.

### Changed — breaking

- **`--env dev` removed** — use `--env local` for local docker-compose mode across the board. Aliases `make dev` / `dev-down` / `dev-logs` are gone; use `local` / `local-down` / `local-logs`. `forktex.dev.json` overlays → `forktex.local.json`. `Dockerfile.dev` → `Dockerfile.local`.
- **SDK deps pinned.** `forktex-intelligence >=1.0.0,<2.0.0` and `forktex-cloud >=1.0.0,<2.0.0`. Upgrade both SDK lines together within the 1.x major.
- **Filesystem paths routed through `forktex_cloud.paths`** — no more hardcoded `.forktex/` literals in the CLI. Direct consumers of `forktex.core.paths` keep the same API (thin wrappers).
- **FSD `start`/`stop`/`logs` atoms** accept `start`/`local`/… only (the `dev` / `dev-down` / `dev-logs` alternatives are dropped from `required_targets`).

### Added

- **V1 `.forktex/` spec**, enforced cross-platform: every subsystem writes through `forktex_cloud.paths`. Schema version stamped at `.forktex/.version`. Canonical gitignore block auto-appended on first run. See [cloud/docs/forktex-directory-spec.md](https://github.com/forktex/cloud/blob/master/docs/forktex-directory-spec.md).
- **Auto `.gitignore` management** — `StateManager.ensure_dir()` routes through `paths.ensure_project_dirs()`, which appends the canonical forktex block idempotently and writes `.forktex/.version`.

### Migration

1. Rename `forktex.dev.json` → `forktex.local.json` and switch `--env dev` usages to `--env local`.
2. Replace `make dev` / `make dev-down` / `make dev-logs` with `make local` / `make local-down` / `make local-logs` (or regenerate Makefiles via `forktex fsd makefile sync --all-packages`).
3. Ensure `forktex-intelligence>=1.0.0` and `forktex-cloud>=1.0.0` resolve cleanly in your env.

## [0.5.0] — prior release

Initial PyPI packaging for the `forktex` CLI. Included agent, cloud commands, FSD, scraper, architecture discovery.
