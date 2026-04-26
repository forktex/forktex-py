# Changelog

All notable changes to the `forktex` CLI are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.4] — 2026-04-26

### Docs

- **README rewritten as a consumer-facing landing page.** Leads with what `forktex` does on its own (chat REPL + agents, tool registry, `arch discover`, `fsd check/report`) before introducing the three platforms — cloud, intelligence, network — as peer "server connections" with the same `connect`/`disconnect` verbs. Brand assets wired up: `./docs/banner.svg` for the header (GitHub-only; PyPI requires absolute URLs), and the hosted `cloud.forktex.com/assets/forktex-{cloud,intelligence,network}-icon-*.svg` SVGs for the three-platform card.
- **Technical lore moved to `./docs/`.** New `docs/cli-reference.md` (full command tree + slash commands + keybindings + a built-in-vs-platform matrix), `docs/credentials.md`, `docs/configuration.md` (env vars, ecosystem, brand asset URL), `docs/development.md` (`make ci`, license headers, sibling-SDK editable installs).

## [1.0.1] — 2026-04-25

### Security

- **`cryptography` floor bumped `>=42.0` → `>=46.0.6,<47.0.0`.** Closes three CVEs disclosed against the 42.x–43.x line: CVE-2024-12797 (TLS verification path), CVE-2026-26007, CVE-2026-34073. Surfaced by `make audit` (pip-audit) which is now part of the `make ci` publish gate.

### Changed — licensing (breaking for downstream re-distributors)

- **Re-licensed AGPL-3.0 + Commercial dual.** The CLI moves from MIT (1.0.0) to AGPL-3.0-or-later with a parallel commercial offering — matching the model used by `forktex/network`. `LICENSE` and `NOTICE` ship at the repo root; every source file carries an SPDX-stamped header. Commercial licensing inquiries: info@forktex.com. The 1.0.0 wheel on PyPI remains under MIT for users who pinned it.

### Added

- **Brand glyphs in the CLI** (`src/forktex/agent/ui/branding/`) — terminal-native ASCII/Unicode logos for forktex / cloud / intelligence / network, faithful to the SVG marks at `cloud.forktex.com/assets/`. Cloud is the full 8-arm radial; network is the diagonal X; intelligence is the 6-arm head-with-body; forktex is the asymmetric 3-prong fork. Each glyph lives in its own `glyphs/<product>.py` data file (no logic), brand colours in `palette.py` (one-line edits), rendering rules (background dot field, halo chars, single-vs-double-line cardinals) in `render.py`. Wired into the bare-`forktex` menu so each facet card carries its own coloured monogram.
- **License-header tooling** — `scripts/license_headers.py check / fix / strip` walks `src/`, `tests/`, `scripts/` and applies the AGPL-3.0+Commercial header idempotently. Wired through forktex.json atoms `license-check`, `license-fix`, `license-strip` and surfaced as `make license-check` / `make license-fix` / `make license-strip`. `make ci` now gates publishes on `license-check`.
- **`make ci` is the publish gateway** — chained as `format-check → lint → license-check → audit → test → build`, then prints "*safe to: make publish-test  /  make publish*". The build step runs `python3 -m build` + `twine check`, so a passing CI proves the artifact is publishable before the network call. `pyright` and `pip-audit` are added to the `dev` dependency group and installed via `poetry install --with dev` in the GitHub Actions workflow. `make typecheck` runs pyright standalone but is **not** part of the `ci` chain yet — there are pre-existing cross-SDK type drifts (e.g. `UserRead.email`, `CollectionListResponse.get`) that need to be aligned with the published SDK shapes before typecheck can gate publishes.
- **FSD makefile generator: override semantics** (`src/forktex/fsd/makefile.py`) — manifest atom overrides now genuinely override standard-catalog atoms instead of appending duplicate Make targets. Two fixes: (1) `_make_target_comment` reads `override.description` when present, so retitling a built-in atom (e.g. relabelling `codegen` to "Not applicable") propagates to the `## help` comment; (2) custom-atom target names are collected before the standard-atom render loop, and any standard atom whose primary make-target collides with a custom one is skipped. Eliminates the duplicate-target warning that previously flagged `license-check` (standard's `license` atom emits `make_targets = ['license-check', 'license-fix']`, which collided with our custom `license-check` override).

### Changed — breaking

- **Python floor bumped 3.11 → 3.12.** Covers Ubuntu 24.04 LTS, Fedora 41+, Homebrew Python on macOS, and Windows 3.12+. Debian 12 stable users on system Python need `apt install -t bookworm-backports python3.12` or deadsnakes. Installer (`scripts/_install_core.py`) detects this and prints OS-specific install hints. Dev target across the project is now Python 3.14; the floor stays portable.

### Added

- **Hosted multi-OS installer** — `curl -sSL install.forktex.com/sh | sh` (Linux/macOS) and `iwr -useb install.forktex.com/ps | iex` (Windows). Prefers `pipx`, falls back to `pip --user` with PEP 668 handling, seeds `~/.forktex/` (`%APPDATA%/forktex/` on Windows). Scripts live in `scripts/install.{sh,ps1}` with shared core logic in `scripts/_install_core.py`; `make installer-build` bundles them into `dist/install/` for hosting.
- **Unified `connect` / `disconnect` credential verb** — identical on every service: `forktex cloud connect`, `forktex intelligence connect`, `forktex network connect`, plus the symmetric `<service> disconnect`. `--new` forces register for intelligence / network. Cloud registration points at the web signup (no programmatic register).
- **`forktex status`** (top-level) — aggregate credential-state table across all three services. Supports `--json` for scripting and `--no-probe` for offline use.
- **`forktex intelligence status`** — operational status command (API health + whoami), matching the shape of `cloud status` and `network status`.
- **Slash-command registry with live autocompletion** (`src/forktex/agent/root_loop/slash.py`) — `/help`, `/status`, `/cards`, `/connect <service> [--new]`, `/disconnect <service>`, `/clear`, `/history`, `/tools`, `/menu`, `/quit`. Tab cycles; as the user types `/`, the dropdown appears live with command descriptions; after `/connect `, services appear with their one-liners.
- **Menu input on `prompt_toolkit.PromptSession`** — arrow keys edit the line, Ctrl+W/U work, up-arrow recalls history, Tab accepts the highlighted completion. No more raw-escape dumps (`^[[A`, `^L`, etc.) in the input.
- **Chat REPL on `prompt_toolkit.Application`** — full-screen layout with input pinned at the bottom, streaming replies that don't stomp the prompt, and service cards hidden by default (toggle with `Ctrl+K` or `/cards`). No more spurious card re-renders after every reply. `Ctrl+H` shows full transcript; `Ctrl+L` clears visible buffer; `Ctrl+D` / `Ctrl+C` exits to menu.
- **Inline connect inside chat** — `/connect network --endpoint …` runs the same `connect_network` implementation used by the CLI; credentials land at `~/.forktex/network.json` without exiting the REPL. Cards flash for 3 s on success.
- **`forktex network`** — new facet group, wired to the `forktex-network` SDK (pinned `>=1.0.0,<2.0.0`). Commands: `connect`, `disconnect`, `status`.
- **Intelligence verbs grouped under the facet** — `forktex intelligence {ask, run, scrape, index-ecosystem, status, connect, disconnect}` so the three services sit at the same level in the CLI tree.
- **Root loop** — bare `forktex` prints per-service cards driven by live auth state; auto-upgrades into the intelligence chat REPL when intelligence is reachable. Interactive chat has no dedicated verb — it *is* the bare invocation. `AgentDriver` Protocol in `forktex.agent.root_loop.driver` reserved for a future local-model driver shipped from the Intelligence SDK.
- **`make dev-link-sdks` / `make dev-unlink-sdks` / `make dev-install`** — editable installs of the three sibling SDK repos (`../cloud/sdk-py`, `../intelligence/sdk-py`, `../network/sdk-py`) for ecosystem development against in-tree sources. `FORKTEX_DEV_SIBLING_SDKS=1` appends `(dev-linked)` to `forktex --version` as a courtesy signal.
- **`prompt_toolkit (>=3.0,<4.0)`** added to dependencies. No conflicts with `rich` (idiomatic pairing: prompt_toolkit for input / layout, rich for formatted output). Pure Python, MIT, ~250 KB installed.

### Changed — breaking

- **`forktex <service> login`** → **`forktex <service> connect`** on all three services. `logout` → `disconnect`. Hard-break, no alias.
- **`forktex intelligence init`** removed earlier in this unreleased cycle; current verb is `forktex intelligence connect`.
- **Slash commands `/login` + `/logout` + `/register`** collapsed into `/connect <service> [--new]` and `/disconnect <service>`. `/connect` is idempotent — tries login, falls back to register for intelligence / network.
- **Top-level `chat` / `ask` / `run` / `scrape`** removed. `chat` is now just bare `forktex`; the others live under `forktex intelligence`.
- **Top-level `init`** (interactive wizard orchestrating intelligence + cloud) removed; run the per-service `connect` commands directly.
- **`forktex auth` group** removed in favour of per-service verbs.
- **Word "facet"** no longer appears in customer-visible text (help panels, error messages, help strings). `Facet` type name and `FACETS` tuple stay as internal code symbols.

### Migration

```bash
# Before                                     # After
forktex cloud login --api-key ftx-…          forktex cloud connect --api-key ftx-…
forktex intelligence init --global           forktex intelligence connect --global
forktex intelligence logout                  forktex intelligence disconnect
forktex network logout                       forktex network disconnect
forktex auth status                          forktex status
forktex auth set <facet>                     forktex <service> connect
forktex auth clear <facet>                   forktex <service> disconnect
forktex chat                                 forktex                        (bare menu → chat)
forktex ask "…"                              forktex intelligence ask "…"
# inside chat:
/login network                               /connect network
/register intelligence                       /connect intelligence --new
/logout cloud                                /disconnect cloud
```

On-disk credential files are unchanged (`~/.forktex/{cloud,intelligence,network}.json`). Nothing to migrate for existing data.

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
