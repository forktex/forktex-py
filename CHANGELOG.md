# Changelog

All notable changes to the `forktex` CLI are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

_(nothing yet)_

## [0.5.0] — 2026-05-14

### Changed

- **Cloud SDK 0.3.0 retires the `ForktexCloudClient` long-form name.**
  `Cloud` is now the only exported client class — the `Cloud =
  ForktexCloudClient` alias has been removed from the SDK and from
  `forktex.cloud.__init__`. Every agent-CLI command (`down`, `up`,
  `deploy`, `server`, `project`, `vault`, `logs`, `status`, `dns`,
  `ssl`, `registry`, `use`, `inspect`, `tree`, `new`) imports `from
  forktex_cloud import Cloud` directly. Consumers still pinned to
  `forktex-cloud<0.3.0` keep working since older SDKs still export
  both names; new code should only reach for `Cloud`.

### Added

- **`forktex.network` Python shim.** Mirrors `forktex.cloud` and
  `forktex.intelligence` — re-exports `NetWork` (canonical, with
  back-compat fallback to `NetworkClient` on older floors),
  `NetworkClient`, `NetworkAPIError`, plus the settings layer
  (`NetworkSettings`, `load_network_settings`, `save_network_global`,
  `save_network_project`). Public Python API now symmetric across all
  three platforms: `from forktex.{cloud,intelligence,network} import
  {Cloud,Intelligence,NetWork}` works the same way.
- **Auth-contract symmetry test** at `tests/test_auth_symmetry.py`.
  Locks the cross-facet contract: every facet in `FACETS` has a
  connect impl with the same kwargs, returns `AuthState` from
  `load_state`, has a credential-file `EntrySpec` marked
  `sensitivity="secret"`, has a public Python shim with the canonical
  class in `__all__`, and `auth/cli.py` doesn't import the long-form
  client classes (only canonical names through the shims). Eight
  assertions — drift fails loudly at gate time.

### Changed

- **`auth/cli.py` migrated to canonical SDK names (hard break).**
  `connect_cloud` uses `Cloud` (was `ForktexCloudClient`).
  `connect_network` uses `NetWork` (was `NetworkClient`).
  `connect_intelligence` uses `Intelligence` (was
  `ForktexIntelligenceClient`); the auth flow bootstraps with a
  placeholder `api_key` since `/auth/login` doesn't validate it, then
  re-constructs `Intelligence` with the real key for verification.
  Methods that don't yet exist on the `Intelligence()` facade
  (`list_orgs`, `create_api_key`) are reached via `intel.client.*` so
  forktex-py imports only `Intelligence` itself from the SDK. The
  symmetry test enforces this going forward — the long-form classes
  cannot be re-imported in `auth/cli.py` without failing CI.

### Added (continued)

- **Chat agent now boots with project grounding.** The bare `forktex`
  REPL's system prompt is composed by `forktex.agent.intelligence.grounding.build_system_prompt`,
  which injects (a) the project's `AGENTS.md` (root or `docs/AGENTS.md`,
  root wins) and (b) the cached `manual@agents` bundle from
  `<project>/.forktex/manual/manual_bundle.json` if `forktex manual
  build` has been run — rules + key concepts (top-N by graph degree) +
  common tasks (few-shots). When the bundle is missing the prompt
  carries a one-line hint suggesting `forktex manual build`. Total
  prompt length capped at 20000 chars with a `[truncated]` marker;
  per-section caps prevent any one source from crowding out others.
  This means an `AGENTS.md` edit (e.g. the recent Cloud SDK + workspace
  atoms section) takes effect on the next chat boot — no code change
  required to teach the agent new conventions.
- **`from forktex.cloud import Cloud` works regardless of SDK floor.**
  The `forktex.cloud` shim re-exports `Cloud` as the friendly public
  name; on sibling sdk-py 0.2.5+ it routes to the SDK's own
  `Cloud = ForktexCloudClient` alias, on PyPI 0.2.4 it falls back to
  a forktex-py-side alias. New code should prefer `Cloud`;
  `ForktexCloudClient` stays exported for back-compat with the ~108
  existing import sites under `forktex.agent.cloud.*`. The fallback
  drops once the dep floor is bumped past 0.2.5.
- **Persistent REPL history.** Bare `forktex` now keeps line history
  across sessions in `<global_config_dir>/repl_history` (typically
  `~/.forktex/repl_history`). Up-arrow recalls previous prompts the
  next time you open the REPL. Powered by
  `prompt_toolkit.history.FileHistory` and shared between the menu
  PromptSession and the chat input buffer. Falls back to in-memory
  history if the global config dir isn't writable.
- **`/exit` slash command** — alias for `/quit`, matches common REPL
  conventions.

### Fixed

- **`/connect` mid-chat no longer breaks the TTY.** The detach/reattach
  pair around the embedded login flow is now wrapped in `try/finally`
  so the prompt_toolkit Application restores the terminal even when
  the connect impl raises (`KeyboardInterrupt`, `SystemExit`, or
  generic `Exception`). A friendly one-liner ("connect <svc>
  cancelled — try again with /connect <svc>") replaces the silent
  drop-back.
- **Stream errors are now classified.** The chat-turn exception
  handler distinguishes transient network blips
  (`httpx.RemoteProtocolError`/`ReadTimeout`/`ConnectError`,
  `asyncio.TimeoutError`, generic `ConnectionError`,
  `IntelligenceAPIError 408/429`) from fatal failures
  (`IntelligenceAPIError 401/403` → suggests `/connect intelligence`;
  other 4xx/5xx). Unknown exceptions render with a debug hint instead
  of a raw traceback. New helper at
  `forktex.agent.root_loop._stream_errors.classify`.
- **Login-cancelled feedback.** The menu's connect dispatcher now
  catches `KeyboardInterrupt` and `SystemExit` together and prints
  "<service> connect did not complete — type 'c' / 'i' / 'n' to
  retry." instead of dropping back to the menu silently.

### Publishing-readiness verdict — bare `forktex` REPL

The `forktex` runtime agent (the bare-invocation chat REPL) is
publish-ready. End-to-end audit:

- Entry point + lifecycle (`forktex.agent.cli`, `forktex.agent.root_loop`).
- Menu UI auto-upgrades to chat when Intelligence is reachable.
- Chat app streams SSE deltas with up to 20 tool-call rounds.
- 12 graph tools + filesystem + git + gated-bash all wired.
- 11 slash commands (`/help`, `/status`, `/cards`, `/connect`,
  `/disconnect`, `/clear`, `/history`, `/tools`, `/menu`, `/quit`,
  `/exit`).
- Persistent history (this release) + clean Ctrl+C/Ctrl+D handling.

Composition with the renamed SDK shapes (`Intelligence()` /
`Cloud()` / `NetWork()`) and `forktex-core`'s graph + catalog
primitives is a follow-up coordinated with sibling-repo PyPI
publishes — see project memory `project_sdk_rename_migration_plan`.

### Changed — breaking

- **`help` atom removed from the catalog.** `make help` is a Makefile
  convention (target listing), not an FSD evidence concept — the
  atom never carried its weight. The Makefile generator now emits a
  `help:` rule as a static preamble (always present, independent of
  the catalog), so `make help` keeps working for every project.
  Catalog drops from 21 → **20 atoms** across 4 domains. The
  `ergonomics` facet (which contained only `help`) is also removed,
  along with its references from L1/L2/L3/L4. FSD catalog version
  bumped `1.2.0` → `1.3.0`.
- **`forktex help` is no longer a recognised CLI command.** Use
  `forktex --help` for the CLI surface (Click's built-in) and
  `make help` for the Makefile target listing. The two surfaces are
  now cleanly separate.

### Fixed

- **Atom dispatch crashed with `'Context' object has no attribute
  'exit'`** when running any `forktex <atom>`. asyncclick's
  ``Context`` doesn't expose a sync-style ``.exit()``; replaced with
  ``sys.exit(rc)`` in both ``forktex.agent.atoms.dispatcher`` and
  the ``forktex.agent.manual`` group's ``invoke_without_command``
  fallback.
- **`forktex cloud connect` would AttributeError on
  `token_resp.accessToken`** because the published
  `forktex_cloud.client.generated.TokenResponse` exposes
  ``access_token`` (snake_case). Updated `agent/auth/cli.py` and
  the regression test in `tests/test_auth_connect.py` accordingly.

### Added

- **Atom catalog as first-class CLI surface.** Every FSD atom now
  has a top-level `forktex <atom>` command, 1:1 with the catalog
  (e.g. `forktex test`, `forktex apply --env local`,
  `forktex acceptance --scope battle`). Variants surface as
  `--service`, `--env`, and repeatable `--scope` flags; resolution
  routes through `forktex.fsd.variants.parse_atom_key` and shells
  out to `make <target>`. Bare `forktex` (no subcommand) keeps the
  runtime-agent REPL. Atom-name collisions: `forktex manual` (no
  subverb) routes to the atom dispatch via the group's
  `invoke_without_command=True` body; `forktex clean` keeps its
  existing `.forktex/` purge behaviour and the *atom* `clean`
  (build-artifact cleanup) is invoked via `make clean`.
- **`ForktexManifest.load(path, env=None)` per-env overlay.** Mirrors
  the cloud SDK's overlay shape: when `env` is provided and a
  `forktex.<env>.json` file sits next to the base manifest, it is
  deep-merged in before pydantic validation. List-of-records merge
  by `id`/`name` key; plain lists overlay-replace. New helper at
  `forktex.manifest._overlay.deep_merge`.
- **`manual` atom (code domain).** Generates a system-wide
  architecture + context manual from the project graph for both
  humans and AI agents. Variants: `manual@arch` (C4),
  `manual@graph` (filesystem inspector + dependency tree),
  `manual@agents` (AI bundle: rules / concepts / few-shots),
  `manual@search` (keyword fuzzy-search over the graph, ranked).
  Catalog grows from 20 → **21 atoms**; L3 cumulative count
  17 → 17 (manual is optional at L3); L4 21 → 22 atoms covered.
  FSD catalog version bumped from `1.1.0` → `1.2.0`.
- **`forktex.manual` Python package.** Public API:
  `generate_manual(graph, scope=...)`, `ManualBundle`, `ManualScope`,
  `SearchIndex`, `SearchHit`. Covered by v1.0.0 semver.
- **`forktex manual` CLI subcommand**: `forktex manual build
  [--scope arch|graph|agents|search]` and `forktex manual search
  <keyword>`. Writes outputs under `<project>/.forktex/manual/`
  (audited via the structure spec).
- **`package/python-library` profile** now has `acceptance` and
  `manual` in `optional` (previously `acceptance` was disabled).
  Library projects that ship a CLI entrypoint can declare a
  meaningful acceptance flow and reach L4.
- **`package/python-sdk` profile** now has `acceptance` in
  `optional` (matching the library profile change). SDKs that
  publish to PyPI can also benefit from the wheel-install acceptance
  pattern.

### Fixed

- **FSD level evaluator now treats profile-disabled atoms (N/A) as
  non-blocking**, matching the facet evaluator's behaviour. Without
  this fix, switching a project to a profile that disables a
  level-required atom (e.g. `apply` for `package/python-library`)
  would silently drop the project from L4 → L0 even though every
  applicable atom was satisfied. Regression test in
  `tests/test_fsd_evaluate.py`.

### Changed — breaking

- **`ci` chord renamed to `gate`.** The catalog's chord trio is
  now `quality / gate / release`. `release` chord composes from
  `gate` (was: from `ci`). Hard break — projects using
  `make ci` must rename to `make gate`. Justification: "CI" is
  industry slang for the merge gate; verb-shaped chord names are
  consistent with the rest of the catalog.
- **forktex-py switched profile from `workspace/python-monorepo` to
  `package/python-library`** and bumped declared `targetLevel` from
  `L3` to `L4`. forktex-py is a single-package Python CLI, not a
  workspace runtime — the new profile is more honest.
  `apply`/`destroy`/`monitor` are now N/A on the FSD report (they
  don't apply to a CLI library).
- **`logs` atom merged into `monitor`.** The runtime-control facet
  now exposes a single `monitor` atom that covers health probes,
  metric scrapes, replica status, **and** live event/log streams.
  Variants like `monitor@local@logs` express the streaming scope
  without a separate atom. The four bundled profiles
  (`workspace/python-monorepo`, `package/python-library`,
  `package/python-sdk`, `docs/knowledge-directory`) and the
  Makefile generator have been resynced.
- **`smoke` removed from the ecosystem vocabulary.** The
  `acceptance` atom no longer accepts `smoke` as a resolver
  alternative or `acceptance@smoke` as a common variant. Use
  `acceptance@battle` (preferred) or `acceptance@e2e` instead.
  `tests/test_smoke.py` has been renamed to `tests/test_battle.py`.

### Added

- **`make acceptance` for forktex-py itself.** The repo's
  `forktex.json` now declares an `acceptance` recipe that builds
  the wheel, installs it into a fresh `python3.14` venv, and
  battle-tests the CLI end-to-end (`forktex --version`, every
  subcommand `--help`, `forktex fsd check` and `forktex graph
  build` against forktex-py itself).
- **CI runs `make acceptance`** after `make ci` on every push and
  PR to `master` (`.github/workflows/ci.yml`).

### Removed

- **Legacy `forktex.agent.fsd.standard` module deleted (~700 lines).**
  Replaced by the JSON catalog at `src/forktex/data/fsd/standard.json`
  loaded via `forktex.fsd.loader.load_standard`. The single remaining
  consumer (`agent/fsd/report.py`) now uses `ISORef` from
  `forktex.fsd.models`. Importers of `forktex.agent.fsd.standard`
  must migrate to `forktex.fsd.models` (`ISORef`, `Atom`, `Facet`,
  `FSDStandard`, …).
- **Orchestra filesystem-bootstrap subsystem retired.** `forktex
  intelligence orchestra resume` and `attach` CLI commands, their
  helpers (`_load_stash`, `_stash_to_env`, `do_attach`,
  `known_idents`, `_CACHE_DIRS` covering `/tmp/forktex-creds/`,
  `~/.config/forktex/`, `~/Desktop/forktex/quick-start/`), and the
  bare-`forktex` REPL's auto-attach hint are all gone. Source the
  bootstrap kit's `export OA_*=…` block directly in your shell; the
  long-term flow is moving to remote MCP. `docs/orchestra-cli.md`
  deleted in the same cut.

### Added (paths + hygiene)

- **Centralized project-path layer** (`forktex.core.paths`):
  `find_project_root`, `require_project_root`, and the new
  `find_ecosystem_root` — the latter consolidates a walk that was
  previously duplicated byte-for-byte across three
  `agent/commands/` modules (`root_agent.py`, `index_ecosystem.py`,
  `ground.py`). Internal callers and the four affected tests now
  use the shared helpers.
- **CI-blocking `tests/test_path_hygiene.py` regression test.**
  Sniffs `src/` and `tests/` for hardcoded `/home/<user>/…` or
  `/Users/<user>/…` absolute paths, `/tmp/forktex-…` literals outside
  `forktex.core.paths`, duplicated ecosystem-root walks, and tests
  bypassing `require_project_root(__file__)` in favour of fragile
  `Path(__file__).resolve().parents[N]` arithmetic. Caught the
  hardcoded `/home/samanu/Desktop/forktex/forktex-py` PROJECT_ROOT
  in two test files that passed locally on the author's workstation
  but failed on GitHub Actions where the runner home differs.

### Changed (canonical SDK names)

- **Internal code uses only canonical SDK names** (`Cloud`,
  `Intelligence`, `NetWork`). Nine modules under
  `src/forktex/agent/` switched away from the legacy long-form
  imports (`ForktexIntelligenceClient`, `NetworkClient`). The
  `forktex.{cloud,intelligence,network}` shims still re-export the
  legacy aliases for one back-compat cycle so existing downstream
  import sites keep working.

### Fixed (CI + security)

- **`urllib3 2.7.0`** — picks up CVE-2026-44431 and CVE-2026-44432.
- **`make build` works in fresh CI venvs.** The Makefile build /
  publish / publish-test targets (sourced from `forktex.json`) now
  invoke `poetry run python -m build` / `… twine check` instead of
  bare `python3 -m build`, so the gate no longer depends on `build`
  + `twine` being on the ambient `PATH`. Both modules are also in
  the `[dependency-groups].dev` declaration.

### Migration — upgrading from `forktex 0.2.6` (latest PyPI)

This block consolidates every breaking change since `0.2.6`. If your
project still uses any of the surfaces below, update before pulling
the new release.

**1. CLI commands removed (in 0.3.0 — surface consolidation).**

| Removed | Replace with |
| --- | --- |
| `forktex arch` | `forktex graph build` + `forktex graph c4` |
| `forktex purge` | `forktex clean` |
| `forktex local` | `forktex cloud up --env local` |
| `forktex git` | use `git` directly |
| `forktex present` | `forktex graph c4 --format html` |
| `forktex overview` | `forktex status` |

**2. Deprecated atom aliases removed (hard break in 0.4.0).** The
`aliases.deprecated` redirect map is gone — projects must declare
canonical atom IDs in `forktex.json`. Make-target → atom rewrite:

| Old target | New atom (+ variant) |
| --- | --- |
| `start`, `up` | `apply` (`apply@local`, `apply@<env>`) |
| `stop`, `down` | `destroy` (`destroy@<env>`) |
| `deploy` | `apply@<env>` |
| `deps` | `install` |
| `typecheck` | `typing` |
| `security-audit`, `audit` | `security` |
| `codegen`, `codegen-check` | `sync@api`, `sync@types` (etc.) |
| `monitoring` | `monitor` |
| `verify`, `e2e`, `smoke`, `battle` | `acceptance@battle`, `acceptance@e2e`, … |

**3. `targetLevel: L5` no longer accepted (hard break in 0.4.0).** The
catalog stops at `L4 Operational`. Update `forktex.json`:

```diff
-  "targetLevel": "L5"
+  "targetLevel": "L4"
```

**4. `logs` atom merged into `monitor` (hard break in 0.5.0).**
Catalog drops from 21 atoms to 20.

```diff
   "fsd": {
     "atoms": {
-      "logs": { "commands": ["docker compose -f .forktex/compose/docker-compose.local.yml logs -f"] }
+      "monitor@local@logs": { "commands": ["docker compose -f .forktex/compose/docker-compose.local.yml logs -f"] }
     }
   }
```

The bundled `monitor` atom's `resolve.any_of` accepts `logs` as a
Make-target name, so existing `make logs` recipes continue to satisfy
the merged atom — only the *atom declaration* in `forktex.json`
changes.

**5. `acceptance@smoke` variant removed (hard break in 0.5.0).**
Use `acceptance@battle` (preferred) or `acceptance@e2e`. `forktex fsd
check` rejects `acceptance@smoke` declarations.

**6. `ci` chord renamed to `gate` (hard break in 0.5.0).**

```diff
-make ci
+make gate
```

If your `forktex.json` declares an explicit `ci` atom override under
`fsd.atoms`, rename the key:

```diff
   "fsd": {
     "atoms": {
-      "ci": { "commands": ["..."] }
+      "gate": { "commands": ["..."] }
     }
   }
```

CI scripts (GitHub Actions, GitLab CI, etc.) invoking `make ci` must
update to `make gate`. The workflow file name (`.github/workflows/ci.yml`)
can stay; only the `make` invocation changes.

**7. New `manual` atom (additive in 0.5.0).** No migration
required — projects can opt in by declaring a `manual` atom recipe in
`forktex.json` (or use `forktex manual build` directly without
declaring an FSD atom).

After applying any of the above, regenerate your `Makefile`:

```bash
forktex fsd makefile sync
```

then verify with `forktex fsd check && make gate`.

## [0.4.0] — 2026-05-08

### Changed — breaking

- **FSD pruned to software delivery only.** The bundled standard at
  `src/forktex/data/fsd/standard.json` drops 26 organisational atoms,
  5 organisational domains (governance / process / compliance /
  supply-chain / financial), 12 organisational facets, and the
  `L5 Compliant` level. The catalog is now **21 atoms across 4
  domains** (`code`, `data`, `infra`, `ops`) with ladder **L0–L4**.
  forktex-py is now positioned as a generic software-tooling library;
  organisational governance scope is out of scope and not preserved.
- **Hard break on deprecated atom aliases.** The `aliases.deprecated`
  redirect map (which kept `start`/`stop`/`up`/`down`/`deploy`/`deps`/
  `typecheck`/`security-audit`/`codegen`/`codegen-check`/`monitoring`/
  `audit`/`verify`/`e2e`/`battle` working as Make targets) is
  removed. Projects must declare new atom IDs explicitly. Chord
  aliases (`quality`, `ci`, `release`) remain.
- **`standard.legacy.json`** (the v1.0.0 catalog backup) is deleted.
  The historical catalog is recoverable from git history if needed.
- **External `forktex.json` files targeting `L5`** will now fail
  validation. Update the `targetLevel` field to `L4` or below.

### Changed

- **Library-wide language cleanup.** Removed ForkTex-ecosystem-internal
  references from docs and source comments (controller-DB column
  model, Hetzner-specific phrasing, "software factory" narrative,
  ISO-grade audit-evidence framing). Integration interfaces (`forktex
  cloud connect`, `@sdk_boundary` pattern, the SDK call shapes) stay.
- **`docs/cloud-boundary.md`** trimmed to the integration contract:
  the 5-lane responsibility split, `@sdk_boundary` audited bridge,
  4-step pipeline, provider-axis dispatch, `scaffold_manifest`
  follow-up. Internal cloud-side details (state-reconciliation deep
  dive, controller DB schema) removed.
- **`docs/configuration.md`** — ecosystem framing rewritten as
  "optional integrations" rather than vendor narrative.
- **`forktex fsd report`** description: "ISO audit evidence" →
  "FSD evidence pack (JSON + HTML)".

## [0.3.0] — 2026-05-08

**0.3.0 is a customer-facing surface rewrite — see *Removed* and the
*Migration* section at the bottom for breaking changes.** Internally
this turns ForkTex's project state into a queryable graph, adds an AOP
write-tracking layer with strict structure-spec enforcement, ships a
live-instance registry, gives the AI agent twelve new graph-aware
tools, and tightens the customer-facing CLI down to nine commands.

> 0.2.7 was an interim version that was never published; its CHANGELOG
> entry has been folded into 0.3.0. The minor bump (0.2.x → 0.3.0)
> signals the breaking command-surface changes documented under
> *Removed* below.

### Added

- **Project + host graph (`forktex graph`)** — typed multi-edge data
  structure capturing packages, domains, modules, libraries, manifests,
  registered projects, write-touches, and AST-extracted import edges.
  - `graph build` writes stable filenames `graph.{json,dsl,html}` into
    `<root>/.forktex/` and `~/.forktex/` (no more `arch-{ts}.*` churn).
  - `graph c4 --format html` — drill-down C4 viewer (Workspace → System
    → Container → Component) with breadcrumbs and URL-hash deep links;
    replaces the legacy `forktex arch` HTML reports.
  - `graph show --format tree|json|dsl` — terminal-friendly views.
  - `graph audit [--strict]` — validates `.forktex/` against the
    structure spec; `--strict` exits non-zero for CI gates.
  - `graph diff BEFORE.json [AFTER.json]` — node + edge diff between two
    snapshots (or live build vs. saved). Useful for impact analysis.
  - `graph importers TARGET`, `graph package REL`, `graph modules GLOB`,
    `graph recent --hours N` — ad-hoc query shortcuts.
  - `graph ecosystem [--include-nested] [--render c4|tree|json|all]
    [--per-project]` — one-shot inspection across every project under a
    parent directory.
  - `graph build --no-imports` opts out of the AST imports pass for
    huge monorepos.
- **Agent-callable graph tools (12 new)** registered alongside the
  existing filesystem / bash / git tools in `ToolServer`:
  `graph_summary`, `list_packages`, `find_package`, `list_domains`,
  `list_modules`, `find_modules`, `package_imports`, `find_importers`,
  `fsd_status`, `recent_writes`, `validate_path`, `ecosystem_matrix`.
- **`forktex serve`** — root-level FastAPI dashboard; serves the graph,
  C4 view, structure spec, live-instance list, and `/healthz` over HTTP.
- **`forktex clean`** (renamed from `purge`) — removes generated
  artifacts, forgets projects that no longer exist, optionally sweeps
  legacy timestamped FSD/arch evidence (`--legacy-evidence`), and
  tightens permissions on every secret-tagged file (`--secure-perms`).
- **Runtime spine.** Per-invocation lifecycle that auto-installs
  `<root>/.forktex/`, registers a host-wide instance record at
  `~/.forktex/instances/<run_id>.json`, runs a 30-second heartbeat for
  long-lived commands (`serve`, REPL), and GCs stale records on the
  next invocation. Signal handlers cleanly close the record on
  Ctrl+C / SIGTERM.
- **AOP write-tracking layer** (`forktex.graph.io_proxy`):
  - `tracked_write` (sync) + `tracked_write_async` (aiofiles) +
    `tracked_append` (atomic JSONL line) — every write into a
    `.forktex/` directory routes through one of these and is validated
    against `forktex.graph.structure` (raises `StructureViolation` on
    unsanctioned paths; `FORKTEX_STRUCTURE_LENIENT=1` downgrades to a
    warning for development).
  - `sys.audit` safety net surfaces any direct `Path.write_text` /
    `open(..., "w")` into `.forktex/` that bypassed the helper.
  - `@sdk_boundary` decorator wraps sibling-SDK calls (e.g.
    `forktex_cloud.bridge.local_compose.write_local_compose`) and
    validates the resulting `.forktex/` diff against the spec.
- **Structure spec** (`forktex.graph.structure`) — canonical
  `EntrySpec` records for everything the project + host `.forktex/`
  directories may contain, with `sensitivity` tagging
  (`public`/`config`/`secret`) and authorised-writer lists. Adds
  `instances/*.json`, `.gitignore` (project + global, defence-in-depth),
  `c4.html`, `backups/**`, `bootstrap.json` entries, and the legacy
  `cloud.json` alias.
- **Engineering query layer** (`forktex.graph.query`) — pure-Python
  primitives over the graph: `get_project_metadata`, `list_packages`,
  `find_package_by_path`, `list_domains`, `list_modules_in_domain`,
  `find_modules`, `imports_of_module`, `importers_of`,
  `packages_depending_on`, `fsd_level_of_package`,
  `files_touched_recently`, `validate_path`, `ecosystem_fsd_matrix`,
  `reverse_dependents`, `manifest_version_range`. Per-process
  Graph cache with mtime-based invalidation.
- **FSD evolution** — `forktex fsd ecosystem` (FSD level matrix across
  every project in a parent dir), `forktex fsd check --recursive`
  (per-nested-project evidence in monorepos), graph build now extracts
  Makefile targets per package and stamps `fsd_level` onto the package
  node so the C4 view reflects real levels.

### Changed

- **Customer-facing CLI tightened to 9 commands.** `agents`, `clean`,
  `cloud`, `fsd`, `graph`, `intelligence`, `network`, `serve`,
  `status`. Help text rewritten to drop ForkTex-internal vocabulary
  ("ecosystem-aware", "RAG collection", "factory brain", "controller",
  "VPS", "Loki/Promtail" by name, "ISMS", "atom").
- **`forktex status` absorbs `forktex info`** — single overview
  showing project + Python + platform + auth state across all
  configured services.
- **`src/{importable}/...` is now the canonical layout.** The
  makefile generator's `app/` heuristic is correctly inverted.
- **C4 export pipeline** writes the C4 projection through the same
  graph the agent tools read, so `forktex graph c4` and the dashboard
  always agree.
- **`agents ground` and `agents root`** rewritten to use *workspace*
  / *project briefings* / *codebase index* terminology rather than
  `AGENTS.md` / `ECOSYSTEM_COLLECTION` / `factory brain`.

### Removed

- **`forktex arch`** subgroup (`arch discover`, `arch multi`,
  `arch report`, `arch serve`) and its templates — superseded by
  `forktex graph` + `forktex serve`. The C4 deliverable is preserved
  via `forktex graph c4`.
- **`forktex info`** — folded into `forktex status`.
- **`forktex purge`** — renamed to `forktex clean`.
- **`forktex local`** — was a multi-project wrapper around
  `cloud up --env local` / `cloud down`; superseded by per-project
  invocations and `forktex graph ecosystem` / `forktex fsd ecosystem`.
- **`forktex git`** — multi-repo git wrapper; users have native
  `git` for this, no special insight to retain.
- **`forktex present`** — consumed an internal `docs/engineering/
  manifest.json` schema; removed from the customer surface.
- **`forktex overview`** — folded into `forktex graph ecosystem` +
  `forktex fsd ecosystem`.
- **Timestamped FSD evidence filenames** (`check-{ts}.json`,
  `report-{ts}.html`, etc.) — runs now overwrite `check.json`,
  `check.html`, `report.json`, `report.html` in place. Use
  `forktex clean --legacy-evidence` to sweep historical files.

### Security

- **`SECURITY.md`** (new): threat model, what's already in place
  (atomic writes, structure-spec enforcement, audit hook, sensitivity
  tagging, defence-in-depth gitignore at three points), and nine
  go-live hardening recommendations.
- **Argv credential redaction** in instance records — masks
  `--api-key=`, `--token=`, `--password=`, `--secret=`,
  `--access-token=`, plus space-separated forms, in
  `~/.forktex/instances/<run_id>.json` so command-line tokens don't
  end up on disk.
- **Agent JSONL history hardened** — `0o600` permissions on POSIX,
  six default redaction patterns (ForkTex API keys, JWTs, Bearer
  headers, PEM blocks, Stripe-shape keys, GitHub tokens), customisable
  via `redact_patterns=[...]`.
- **`forktex clean --secure-perms`** — walks every `secret`-tagged
  spec entry and chmods `0o600` (POSIX). Implements SECURITY.md §A.
- **Bash-tool gating** — `ToolServer(..., enable_bash=False)` plus
  `FORKTEX_DISABLE_BASH=1` env var lets autonomous deployments deny
  `bash_execute` while keeping the rest of the agent tool surface.
- **`forktex graph audit --strict`** — CI gate that fails the build
  on any unknown or missing-required entry under `.forktex/`.

### Tests

- **354 tests pass (was 168).** New suites: io_proxy (sync + async +
  classify + lenient), registry (round-trip + dedupe + reconcile),
  structure (spec + audit + audit_tree on monorepo fixtures), runtime
  (instance lifecycle, decorators), graph query primitives, AST
  imports edges (with skip-list verification), graph CLI
  (diff/importers/package/modules/recent), agent tools round-trip,
  argv redaction, agent-history hardening, `clean --secure-perms`,
  `ToolServer` bash-gating.
- **Auto-isolated `~/.forktex/`** per test via an autouse
  `isolated_home` fixture — pre-existing tests that wrote credentials
  into the real registry no longer leak.

### Docs

- **README** updated for the new surface — graph + C4 + serve + clean
  + status replace the arch / info / purge references.
- **`docs/cli-reference.md`** rewritten with the 9-command shape and
  the full graph subcommand tree.
- **`docs/cloud-boundary.md`** (new) — responsibility map between
  forktex-py and the forktex-cloud SDK; documents the
  `@sdk_boundary` audited bridge pattern and the
  `scaffold_manifest` follow-up.

### Migration

Each removed command and where its capability lives now:

| Removed in 0.3.0 | Replacement |
| --- | --- |
| `forktex arch discover` / `arch report` / `arch serve` / `arch multi` | `forktex graph build` (data) + `forktex graph c4 --format html` (HTML) + `forktex serve` (live dashboard) |
| `forktex info` | `forktex status` (folded in) |
| `forktex purge` | `forktex clean` (renamed; same flags + `--legacy-evidence`, `--secure-perms`) |
| `forktex local` | `forktex cloud up --env local` per project, or `forktex graph ecosystem` / `forktex fsd ecosystem` for multi-project views |
| `forktex git` | native `git` (no special insight to retain) |
| `forktex present` | removed (consumed an internal manifest schema) |
| `forktex overview` | `forktex graph ecosystem` + `forktex fsd ecosystem` |

On-disk credential files and `.forktex/` layouts are unchanged from
0.2.x. Nothing to migrate for existing data.

## [0.2.6] — 2026-05-04

### Added

- **Cloud agent expansion.** New subcommands wired into `forktex cloud`: `new` (project scaffolding), `use` (active-project switcher), `inspect` (deployment introspection), `tree` (resource topology view), plus internal `deployment.py`, `provider.py`, and `registry.py` modules. The `up`, `logs`, `dns`, `ssl`, and `vault` flows were reworked alongside to share the new provider/registry abstractions.

### Changed

- **Settings-module hygiene** across `agent/cloud`, `agent/intelligence`, and `agent/network` — minor refactors to align the three platform settings surfaces.

## [0.2.5] — 2026-04-28

### Fixed

- **`make test` now runs against the project venv (Python 3.14) via `poetry run pytest`** — previously the bare `pytest` resolved to the system interpreter (Python 3.12), which couldn't parse PEP 758 unparenthesized `except` clauses (`except json.JSONDecodeError, OSError:`) that ruff emits when targeting 3.14. Tests collected with nine `SyntaxError`s on a fresh checkout. The `test` and `test-cov` atoms in `src/forktex/fsd/makefile.py` and the `test` override in `forktex.json` were updated, and the Makefile re-synced with `forktex fsd makefile sync`.

### Docs

- **README rewritten as a consumer-facing landing page.** Leads with what `forktex` does on its own (chat REPL + agents, tool registry, `arch discover`, `fsd check/report`) before introducing the three platforms — cloud, intelligence, network — as peer "server connections" with the same `connect`/`disconnect` verbs. Brand assets wired up: `./docs/banner.svg` for the header (GitHub-only; PyPI requires absolute URLs), and the hosted `cloud.forktex.com/assets/forktex-{cloud,intelligence,network}-icon-*.svg` SVGs for the three-platform card.
- **Technical lore moved to `./docs/`.** New `docs/cli-reference.md` (full command tree + slash commands + keybindings + a built-in-vs-platform matrix), `docs/credentials.md`, `docs/configuration.md` (env vars, ecosystem, brand asset URL), `docs/development.md` (`make ci`, license headers, sibling-SDK editable installs).

## [0.2.3] — 2026-04-25

### Security

- **`cryptography` floor bumped `>=42.0` → `>=46.0.6,<47.0.0`.** Closes three CVEs disclosed against the 42.x–43.x line: CVE-2024-12797 (TLS verification path), CVE-2026-26007, CVE-2026-34073. Surfaced by `make audit` (pip-audit) which is now part of the `make ci` publish gate.

### Changed — licensing (breaking for downstream re-distributors)

- **Re-licensed AGPL-3.0 + Commercial dual.** The CLI moves from to AGPL-3.0-or-later with a parallel commercial offering; every source file carries an SPDX-stamped header. Commercial licensing inquiries: info@forktex.com.

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

## [0.2.2] — 2026-04-24

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

## [0.0.x] — pre-history (initial PyPI packaging)

Initial PyPI packaging for the `forktex` CLI. Included agent, cloud commands, FSD, scraper, architecture discovery. (Originally tagged `0.5.0` before the project re-cut its semver line at `0.2.0`; renamed to avoid colliding with the current `0.5.0` release.)
