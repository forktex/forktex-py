# Changelog

All notable changes to the `forktex` CLI are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

_(nothing yet)_

## [0.5.2] — 2026-05-17

- `forktex --version` now reads from package metadata (was hardcoded; reported `0.5.0` on the 0.5.1 wheel).

## [0.5.1] — 2026-05-17

- Bumped `forktex-intelligence` to `^1.5.0`; migrated to the V1.5 SDK shape.
- Removed `forktex intelligence orchestra` subcommand (backend dropped upstream).

## [0.5.0] — 2026-05-14

- Cloud SDK 0.3.0 retires `ForktexCloudClient`; use `Cloud` instead (back-compat alias kept).
- Added `forktex.network` Python shim; public Python API now symmetric across cloud / intelligence / network.
- Added auth-contract symmetry test (`tests/test_auth_symmetry.py`) — drift fails CI.
- `auth/cli.py` migrated to canonical SDK names (hard break, no alias re-import).
- Chat agent boots with project grounding (composes `AGENTS.md` + `manual@agents` bundle).
- Persistent REPL history at `~/.forktex/repl_history`; new `/exit` slash command.
- `/connect` mid-chat no longer breaks the TTY; stream errors classified; clearer login-cancelled messages.
- **Breaking**: `help` atom removed from catalog (`make help` stays as Makefile preamble).
- **Breaking**: `forktex help` removed — use `forktex --help` or `make help`.
- `urllib3` bumped to 2.7.0 (CVE-2026-44431/44432).
- Internal code uses only canonical SDK names; shims keep long-form aliases for one cycle.
- **Breaking**: `logs` atom merged into `monitor` (catalog 21 → 20 atoms).
- **Breaking**: `acceptance@smoke` variant removed — use `acceptance@battle` or `acceptance@e2e`.
- **Breaking**: `ci` chord renamed to `gate`; `make ci` → `make gate`.
- Added `manual` atom (additive) — `forktex manual build [--scope arch|graph|agents|search]`.
- forktex-py profile switched `workspace/python-monorepo` → `package/python-library`; targetLevel L3 → L4.
- Added `make acceptance` for forktex-py + CI runs it after `make gate`.
- Removed legacy `forktex.agent.fsd.standard` module (~700 lines) — use `forktex.fsd.models`.
- Orchestra filesystem-bootstrap subsystem retired (`forktex intelligence orchestra {resume,attach}`).
- Centralized project-path layer (`forktex.core.paths.find_ecosystem_root`); regression test for hardcoded `/home/<user>/...` paths in CI.

## [0.4.0] — 2026-05-08

- **Breaking**: FSD pruned to software delivery only — catalog now 21 atoms / 4 domains / L0–L4 (removed 26 organisational atoms + `L5`).
- **Breaking**: Deprecated atom-alias redirect map removed — declare canonical atom IDs.
- **Breaking**: `targetLevel: L5` now rejected — update to `L4` or below.
- Removed ForkTex-internal vocabulary from docs and source comments.

## [0.3.0] — 2026-05-08

- Customer CLI tightened to 9 commands: `agents`, `clean`, `cloud`, `fsd`, `graph`, `intelligence`, `network`, `serve`, `status`.
- Added `forktex graph` (build / c4 / show / audit / diff / importers / package / modules / recent / ecosystem) — typed multi-edge project + host graph.
- Added 12 agent-callable graph tools to `ToolServer` (`graph_summary`, `find_importers`, `fsd_status`, ...).
- Added `forktex serve` (FastAPI dashboard with graph + C4 + structure spec + healthz).
- Added `forktex clean` (renamed from `purge`; `--legacy-evidence`, `--secure-perms`).
- Added runtime spine — per-invocation instance record + 30s heartbeat for long-lived commands.
- Added AOP write-tracking (`forktex.graph.io_proxy`) — `tracked_write` + `@sdk_boundary` decorator validate against the structure spec.
- Added engineering query layer (`forktex.graph.query`) — pure-Python primitives over the graph with mtime-invalidated cache.
- `forktex status` absorbs `forktex info`; `src/{importable}/...` is canonical layout.
- **Breaking**: removed `arch`, `info`, `purge`, `local`, `git`, `present`, `overview`.
- Added `SECURITY.md`; argv credential redaction; agent JSONL history hardened (0o600 + redaction patterns).
- Added `forktex graph audit --strict` CI gate; bash tool gating via `enable_bash=False` / `FORKTEX_DISABLE_BASH=1`.
- 354 tests pass (was 168) — new suites cover io_proxy, registry, structure, runtime, graph query, AST imports, graph CLI, agent tools, redaction, history hardening.

## [0.2.6] — 2026-05-04

- Cloud agent expansion: `new`, `use`, `inspect`, `tree` subcommands; reworked `up` / `logs` / `dns` / `ssl` / `vault` over new provider/registry abstractions.
- Settings-module hygiene across cloud / intelligence / network facets.

## [0.2.5] — 2026-04-28

- Fixed `make test` running against system Python 3.12 instead of project venv (PEP 758 syntax errors on fresh checkout).
- README rewritten as a consumer-facing landing page; technical lore moved to `./docs/`.

## [0.2.3] — 2026-04-25

- **Breaking** (licensing): re-licensed AGPL-3.0 + Commercial dual.
- Security: `cryptography` bumped `>=42.0` → `>=46.0.6,<47.0.0` (CVE-2024-12797, CVE-2026-26007, CVE-2026-34073).
- Added brand glyphs in the CLI (`src/forktex/agent/ui/branding/`).
- Added license-header tooling (`make license-{check,fix,strip}`).
- `make ci` is now the publish gateway (format-check → lint → license-check → audit → test → build).
- **Breaking**: Python floor bumped 3.11 → 3.12.
- Added hosted multi-OS installer (`curl … | sh`, `iwr … | iex`).
- Unified `connect` / `disconnect` credential verbs across all three services.
- Added `forktex status` (top-level credential aggregate) and `forktex intelligence status`.
- Slash-command registry with live autocompletion; menu + chat REPL on `prompt_toolkit`.
- Inline `/connect` inside chat; service cards toggle with `Ctrl+K`.
- Added `forktex network` facet (pinned `forktex-network >=1.0.0,<2.0.0`).
- Intelligence verbs grouped under the facet: `forktex intelligence {ask, run, scrape, index-ecosystem, status, connect, disconnect}`.
- Root loop: bare `forktex` shows per-service cards; auto-upgrades to chat REPL when intelligence is reachable.
- Added `make dev-link-sdks` / `dev-unlink-sdks` / `dev-install` for editable sibling-SDK installs.
- **Breaking**: `<service> login` → `connect`; `logout` → `disconnect`; `/login` + `/logout` + `/register` → `/connect [--new]` + `/disconnect`.
- **Breaking**: top-level `chat`, `ask`, `run`, `scrape`, `init`, `auth` removed; chat is bare `forktex`.

## [0.2.2] — 2026-04-24

- V1 release; classifier flipped to `Production/Stable`; SemVer contract from this point.
- **Breaking**: `--env dev` removed — use `--env local`. `make dev` / `dev-down` / `dev-logs` → `local` / `local-down` / `local-logs`.
- **Breaking**: SDK deps pinned `forktex-intelligence >=1.0.0,<2.0.0` and `forktex-cloud >=1.0.0,<2.0.0`.
- **Breaking**: filesystem paths routed through `forktex_cloud.paths`; no hardcoded `.forktex/` literals.
- Added V1 `.forktex/` spec — schema version at `.forktex/.version`, canonical gitignore block auto-appended.

## [0.0.x] — pre-history

Initial PyPI packaging for the `forktex` CLI. (Originally tagged 0.5.0 before semver re-cut at 0.2.0.)
