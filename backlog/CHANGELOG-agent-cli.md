# Changelog

All notable changes to the `forktex` CLI are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.8.1] — 2026-06-03 — Stabilization: CI realignment, dependency floor, cleanup

#### Changed

- **Merge-guard chord realigned to `ci`** (FSD catalog 1.3.0 → 1.4.0). The v1.2.0 rename `ci`→`gate` is reverted: the pre-merge chord is `make ci` again, matching the canonical FSD `ci` atom (*"CI Gate"*) and the `standard.quality-pipeline` doctrine. `make verify`/`release`, the generated `Makefile`, and the CI workflow all reference `ci`; no deprecated alias is kept.
- **`forktex-core` floor raised to `>=2.4.0`.** The knowledge subsystem uses the 2.4.0 `fractal` serialize API (`serialize_node`/`serialize_patch`/`load_patch`); `poetry.lock` is refreshed so CI installs a wheel that ships those symbols (fixes the `make ci` test-collection `ImportError`).

#### Removed

- **Dead compatibility shims** `forktex.models.architecture` and `forktex.models.manifest` (zero importers; the canonical homes are `forktex.architecture.models` / `forktex.manifest.models`, already resolved by the `forktex.models` lazy loader).

#### Fixed

- Resolved a stale `forktex.json` package version (`0.5.0` → `0.8.1`) and the `importlib.resources.path` `DeprecationWarning` in the FSD test suite (now `resources.files()`).

## [0.8.0] — 2026-06-03 — `forktex.substrate`, bucketed `.forktex/`, filesystem-free libraries, run-anywhere

**BREAKING CHANGES** (hard break, no migration shims — existing on-disk `.forktex/` state is regenerated; only the committed `knowledge/` bucket keeps its path). Implements Ring 1 + run-anywhere of `standard.forktex-architecture`.

#### Added

- **`forktex.substrate`** — the single filesystem authority. Unifies the path factories (moved out of `forktex_cloud.paths`), the `.forktex/` spec (`EntrySpec`/`PROJECT_SPEC`/`GLOBAL_SPEC`, formerly `forktex.graph.structure`), and the audit surface. `forktex-py` is now the only component that knows `.forktex/` exists.
- **Run-anywhere.** `@needs_project(soft=True)` lets commands degrade in a bare directory instead of erroring; `forktex arch build --scope os`, `knowledge search`, and the agent all run with no `forktex.json`. Writes lazily create `.forktex/` (init-on-first-write). `knowledge search` with no sources prints a hint instead of failing.
- **`forktex serve` — one generic tool API (HTTP + MCP).** A single FastAPI app (`forktex.api`) mounts every tool group at a root path — `/knowledge`, `/arch`, `/fsd` — over the *same* `Tool` registry the CLI and agent loop use; each tool is a typed `POST /{domain}/{op}`. `fastapi_mcp` rides the whole app so every route is also an MCP tool at `/mcp`. Optional `[mcp]` extra (`fastapi-mcp`); the stdio `knowledge mcp` reuses the same `mcp` lib. The `arch serve` graph viewer is folded in under `/arch` (one server, not one-per-command).
- **`knowledge ingest`** — bulk-import a source (ecosystem `AGENTS.md` → remote vector store); absorbs the former `intelligence index-ecosystem`.
- **`chat --ecosystem`** — ground the agent on the whole workspace (parent `docs/AGENTS.md` + the cross-project knowledge graph); absorbs the retired `agents root`.
- **`agent/tools/catalog.py`** — the central tool-builder catalog (`build_group`/`compose`); the two `ToolServer`s and the API all compose from it (one source, no divergent compositions).

#### Changed

- **`graph` + `manual` merged into `arch`.** `arch build` projects the graph diagrams *and* the agent-grounding `manual_bundle.json` from a single graph build (was a double build); `arch search` is the merged keyword index. Grounding namespace is now `knowledge` + `arch`.

- **Bucketed `.forktex/` layout** (schema version 1 → 2), organized by lifecycle: `knowledge/` (committed) · `secrets/` (creds, vault, keys, `.env`, cloud/intelligence/network config) · `cache/` (graph, c4, manual, compose, observability, fsd evidence, data, db/redis, backups) · `state/` (instances, servers, agent history). Root markers `.version`/`.gitignore`/`config.json` stay at the `.forktex/` root.
- **`forktex_cloud` is filesystem-free (2.0.0).** `forktex_cloud/paths.py` is **deleted**; the bridge emits pure compose data (sibling `./observability` + `./data` binds) with `render_observability_configs()`; `get_secrets_provider(vault_root=…)` takes a caller-supplied path; `write_local_compose` moved into forktex-py (writes via `tracked_write`). The SDK no longer knows the `.forktex/` layout. forktex-py now requires `forktex-cloud >=2.0.0`.
- `forktex.graph.structure` is a back-compat shim re-exporting `forktex.substrate.spec`; the touch registry moved to `state/registry.json`.

#### Removed

- **`agent/commands/` package** (the pre-0.7 `forktex agents` group's tail): `agents.py`, `index_ecosystem.py` (→ `knowledge ingest`), `root_agent.py` (→ `chat --ecosystem`), and the dead `ground.py` AGENTS.md scaffolder. The top-level `graph` and `manual` commands are gone (merged into `arch`).

#### Fixed

- Path-literal bugs that bypassed the factories (cloud + intelligence settings wrote flat `intelligence.json`/`cloud.json`; `instance.py` + graph exporters wrote flat) now route through the bucketed factories.

#### Deferred

- Full SDK purity (manifest_data-only client + `FernetCipher` extraction) — the client still reads `<project>/forktex.json` as input; `FernetVault` does I/O on a caller-supplied path.
- A resilient node loader in `forktex_core.fractal` (skip + warn on one malformed node instead of failing the whole knowledge load) — cross-repo core change.
- Deleting the `/ecosystem/` surrogate (gated on confirming essentials graduated). `StateManager` + the top-level service re-exports are **kept** (load-bearing — verified by audit, not legacy). The docs manifest is now generated from frontmatter (done).
- _Done since:_ the generic knowledge adapters (`generic_markdown` / `code_index` — point forktex at any markdown tree / codebase, ad-hoc via `knowledge … --source ADAPTER:PATH` or declared in `forktex.json [knowledge].layers`); local-first `knowledge ingest` (writes nodes with no Intelligence; `--remote` opt-in); the agentic engine domain (`agent/engine/`); and the `ecosystem`→`workspace` rename.

## [0.7.0] — 2026-06-03 — Final root taxonomy + `.forktex/` fingerprint standard

**BREAKING CHANGES** — the root command tree was cut from 31 to 10 deliberate keys, no aliases. The rationale + design are recorded in `convention.root-taxonomy` (a recycled lesson in `forktex-py/.forktex/knowledge/`) and the new `standard.forktex-fingerprint`.

#### Removed

- **All FSD-atom CLI registrations** — `forktex test` / `build` / `format` / `lint` / `typing` / `security` / `license` / `install` / `publish` / `sync` / `docs` / `backup` / `seed` / `apply` / `destroy` / `monitor` / `rollback` / `acceptance` (19 commands). The atoms were a parallel implementation of the project's Makefile; `make` already owns lifecycle. `forktex fsd check` is unchanged (reads the static Makefile; never depended on atom dispatch). Migration: run `make <atom>` instead of `forktex <atom>`. The dispatcher in `forktex.agent.atoms` remains importable for downstream tooling that needs to construct atom Make targets programmatically; only the CLI registration is gone.
- **`forktex status`** → `forktex auth` (see Added). Cross-service credential aggregator is now the auth domain's default action.
- **`forktex network`** (the group: `status`, `connect`, `disconnect`) → `forktex auth network <verb>`. The `forktex_network` SDK is unchanged for Python consumers.
- **`forktex intelligence`** (the group) — dissolved. Specific renames:
  - `forktex intelligence ask` → use `forktex chat` (interactive) or `forktex run --no-tools` (one-shot, scriptable).
  - `forktex intelligence run` → `forktex run`.
  - `forktex intelligence scrape` → use `forktex chat` (browser becomes a tool inside the agent loop).
  - `forktex intelligence index-ecosystem` → `forktex knowledge ingest` (deferred; until landed, the prior path stays available via `python -m forktex.agent.commands.index_ecosystem`).
  - `forktex intelligence connect / disconnect / status` → `forktex auth intelligence connect / disconnect`, `forktex auth`.
- **`forktex agents`** (the group: `list`, `show`, `cancel`, `ground`, `root`) — dissolved.
  - `list / show / cancel` removed (rare process audit; inspect `.forktex/agents/history/` directly when debugging).
  - `ground refresh` deferred-merge into `forktex manual build` (until landed, callable via `python -m forktex.agent.commands.ground`).
  - `root` (ecosystem-scoped REPL) deferred-merge into `forktex chat --ecosystem` (until landed, callable via `python -m forktex.agent.commands.root_agent`).
- **`forktex mcp`** → `forktex knowledge mcp` (the MCP server only ever served knowledge tools).
- **`forktex serve`** → `forktex graph serve` (the FastAPI viewer only ever browsed the project graph).
- **`forktex knowledge ask`** → `forktex knowledge search` (frees `ask` semantics for the LLM agentic verbs; `search` is the honest verb for ranked-token doc-space query).

#### Added

- **`forktex chat`** — explicit alias for the bare-`forktex` chat REPL. Discoverable in `--help`; bare invocation is preserved.
- **`forktex run <task>`** — orchestrated agentic task with tools (promoted from `forktex intelligence run`).
- **`forktex auth`** — cross-service sign-in surface. Bare `forktex auth` prints the aggregated status across cloud / intelligence / network (the same surface that used to live at `forktex status`). Per-service subgroups expose `connect` / `disconnect`: `forktex auth cloud connect`, `forktex auth intelligence connect`, `forktex auth network connect`. Single mental model, one place.
- **`forktex knowledge mcp`** — the MCP stdio server is now a `knowledge` subcommand.
- **`forktex graph serve`** — the FastAPI viewer is now a `graph` subcommand.
- **`forktex.agent.cli_help.CATEGORIES`** — single source of truth for the `--help` taxonomy. Adding or moving a top-level command is one edit here. The renderer (`forktex.agent.lazy_group.AsyncLazyGroup.format_commands`) groups commands into `Core` / `Grounding` / `Services` / `Housekeeping` sections, `make help`-style: cyan name padded to 22 chars, two-space indent, description after. Cyan on TTY only.
- **`docs/engineering/standards/forktex-fingerprint.md`** (pinned). The on-disk surface (`.forktex/` project-scope + `~/.forktex/` global-scope) is now a documented standard: every file declared in `forktex.graph.structure.PROJECT_SPEC` / `GLOBAL_SPEC`, every write validated by `forktex.graph.io_proxy.tracked_write`. Adding a new on-disk artefact requires an `EntrySpec` first.

#### Changed

- **`forktex.graph.structure.PROJECT_SPEC` clarifications** — the `cloud.json` and `conversation_*.json` entries are now explicitly marked `LEGACY` in their purpose strings, with notes pointing at the V1 canonical paths (`cloud/config.json` and `agents/history/*.jsonl`) and the deferred 0.8.0 milestone for actual removal. The `manual/**` entry now names each of the four output files individually with their reader (`manual_bundle.json` is the load-bearing one — read by `intelligence.grounding`; the others are advisory or browser-only).
- **`forktex.agent.knowledge.cli.knowledge`** and **`forktex.agent.graph.cli.graph`** are now `AsyncLazyGroup` subclasses so subgroup nesting can be lazy (the new `knowledge mcp` and `graph serve` registrations don't load their heavy deps until invoked).
- **`PROJECT_SPEC` now covers the full live `.forktex/` footprint.** A full-ecosystem audit (`structure.audit` across all 18 nested `.forktex/` dirs) found 77 drift entries — almost all spec *under-coverage*, not cruft. Added `EntrySpec`s for files real workflows already produce: `.env` (compose env, secret), `db/**` + `redis/**` (per-service build contexts the cloud SDK tarballs), `state/backups/**` (pre-deploy DB snapshots, secret), and `knowledge/README.md` (seeded by `knowledge init`). The legacy `./.forktex/architecture/**` tree (49 superseded arch dumps at the monorepo root) was deleted. Result: 77 → 4 residual (incidental missing `.gitignore`/`.version` that self-heal on next invocation, plus one stray user script).
- **`forktex knowledge init` now produces a spec-clean `.forktex/`.** It runs the standard lifecycle bootstrap (`lifecycle.install_project`) before scaffolding, so `.version` + the defence-in-depth `.gitignore` are present, and writes its README through `tracked_write` (kind `knowledge_readme`) instead of a raw side write. A knowledge-only init used to leave a directory that failed its own audit. Regression-guarded by `test_init_produces_spec_clean_forktex_dir`.
- **Grounding index prioritises project-local knowledge.** `intelligence.grounding._knowledge_section` now ranks overlay-layer (project) nodes ahead of the base docs catalog in the bounded index, so project lessons aren't starved out of the agent's system prompt as the global corpus grows (it had crossed 108 nodes). Pinned tier unchanged.
- **Stale post-rename strings fixed.** `knowledge init`'s "Next:" hints, its README template, the `init` module docstring, and the grounding system-prompt blurb all referred to the pre-0.7.0 `forktex knowledge ask` / `forktex mcp`; updated to `forktex knowledge search` / `forktex knowledge mcp`.
- **`test_cli_taxonomy` snapshot now runs under `--user` editable installs.** The autouse `isolated_home` fixture repoints `HOME`, which hid a `pip install --user -e .` editable `.pth` from the clean `--help` subprocess (`ModuleNotFoundError: No module named 'forktex'`). The test now pins `PYTHONPATH` to the running interpreter's `sys.path` so module resolution is HOME-independent.

#### Performance

- `forktex --help` cold-start measured **0.84 s** on the dev workstation (CP2 baseline 1.66 s; under the < 2 s budget set in the v1 plan).

#### Deferred to a follow-up

The user-facing IA contract is in. These three internal-logic moves are deferred (`forktex.agent.commands.*` modules are still importable on demand for any remaining callsites):

- `forktex knowledge ingest` absorbing `forktex.agent.commands.index_ecosystem` (the body is ready; the CLI registration + flag wiring is the remaining work).
- `forktex manual build` absorbing `forktex.agent.commands.ground.refresh` (briefing regeneration becomes part of bundle generation).
- `forktex chat --ecosystem` switching the grounding scope to replace `forktex agents root`.

## [0.6.0] — 2026-05-17

- **Breaking**: forktex-cloud SDK upgrade to 1.0.0 — V1 multi-server manifest schema.
  - `cloud.gateway` removed at manifest top level; per-server gateways under `infrastructure.servers[].gateway`.
  - `gateway.domains: [{host, primary}]` collapsed to `gateway.domain: str` + `gateway.sans: list[str]`.
  - `infrastructure.{provider,flavour,region,image}` moved into `infrastructure.servers[].*` (wrapped in `InfrastructureBundle`).
  - New typedefs exposed: `InfrastructureBundle`, `ServerSpec`. Legacy `GatewayDomain` retained for back-compat (re-exported, unused internally).
  - `SSLConfig` gained `zerossl` provider literal + `acme_server`/`eab_kid`/`eab_key` fields.
  - `ForktexManifest.primary_domain` now reads `infrastructure.servers[primary].gateway.domain`.
  - `forktex cloud new --domain <D>` builds V1-shaped overrides under `infrastructure.servers[primary].gateway`.

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
