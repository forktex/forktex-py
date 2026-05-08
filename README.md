<p align="center">
  <img src="./docs/banner.svg" alt="forktex" height="96">
</p>

<p align="center">
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/v/forktex.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/pyversions/forktex.svg" alt="Python"></a>
  <a href="https://github.com/forktex/forktex-py/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/forktex.svg" alt="License"></a>
</p>

<p align="center"><em>A local AI-engineering CLI. Optionally talks to three ForkTex platforms.</em></p>

`forktex` ships as a single binary. By itself it gives you an agent that reads your repo, runs commands, writes patches, audits your delivery standard, and discovers your architecture — no account required. Plug in any of the three ForkTex platforms (cloud, intelligence, network) and the same CLI gains LLM reasoning, infra deploys, and identity / projects / channels.

---

## Install

**One-liner** (Linux / macOS):

```bash
curl -sSL install.forktex.com/sh | sh
```

**One-liner** (Windows, PowerShell 5.1+):

```powershell
iwr -useb install.forktex.com/ps | iex
```

The installer detects Python ≥ 3.14, prefers `pipx` (isolated install), falls back to `pip --user`, and seeds the config directory automatically.

**Manual:**

```bash
pipx install forktex      # recommended — isolates deps
pip install --user forktex
```

Requires **Python 3.14+**. Tested on 3.14.

---

## Built-in — works with zero credentials

Everything in this section runs without connecting to any platform. The CLI ships its own agents, tools, architecture mapper, and delivery-standard checker.

### 🎛  Chat REPL with agents

Bare `forktex` opens the menu. The two heavyweight agents live under `forktex agents`:

```bash
forktex                  # menu (auto-upgrades to chat when intelligence is connected)
forktex agents root      # persistent ecosystem-aware agent — reads AGENTS.md,
                         # the C4 snapshot, and your full project context as system prompt
forktex agents ground    # regenerate AGENTS.md across sibling repos
forktex agents list      # history of agent runs
forktex agents show <id> # inspect one run
```

### 🛠  A real tool surface, not a wrapper

The agent calls into a single tool registry — the same shape an MCP server would expose, just in-process:

| Tool        | What it covers |
|-------------|----------------|
| filesystem  | `read_file`, `write_file`, `patch_file`, `delete_file`, `list_directory`, `glob_search`, `grep_search` |
| bash        | command execution with streaming output and timeouts |
| git         | `status`, `log`, `diff`, `blame`, `commit`, `push` |
| graph       | `graph_summary`, `list_packages`, `find_package`, `list_domains`, `list_modules`, `find_modules`, `package_imports`, `find_importers`, `fsd_status`, `recent_writes`, `validate_path`, `ecosystem_matrix` |
| web         | DuckDuckGo `web_search` + Playwright-rendered `web_fetch` |
| scraper     | 12-tool stateful browser session (navigate, click, type, fill, screenshot, …) |

> **About MCP:** the CLI itself is *MCP-style* (one registry, structured calls) but does not run an MCP server. The MCP endpoint lives on the platform side — see [`cloud`](#three-platforms--one-cli) and its `/api/mcp`.

### 🗺  Project graph + C4 architecture

```bash
forktex graph build            # writes graph.{json,dsl,html} into .forktex/
forktex graph c4 --format html # drill-down C4 view (Workspace → System → Container → Component)
forktex graph show             # rich tree view in your terminal
forktex graph diff             # impact analysis vs an older snapshot
forktex graph importers httpx  # who imports this library/module?
forktex graph ecosystem -b ../ # walk every forktex.json under a parent dir
forktex serve                  # live web dashboard at http://localhost:4444
```

Builds a typed multi-edge graph of your packages, domains, modules, libraries, and AST-extracted imports. The same data feeds the Structurizr DSL, the standalone HTML page, and the agent's tool layer — no duplicate filesystem walks.

### ✅  ForkTex Standard for Delivery

```bash
forktex fsd check          # profile-driven Make-target audit (per-atom, per-facet, per-level)
forktex fsd report         # JSON + HTML evidence pack
forktex fsd ecosystem      # FSD level matrix across every project under a parent dir
forktex fsd makefile sync  # regenerate Makefile from forktex.json atoms (don't hand-edit)
```

`fsd check` evaluates each project against profiles like `workspace/python-monorepo` or `package/python-library`, runs the atom commands declared in `forktex.json`, and reports satisfied / failed / skipped per atom plus per-level achievement. After a successful check, the FSD level is stamped onto the package node in `graph.json` so the C4 view reflects it.

#### The catalog at a glance

**21 atoms across 4 domains** — a software-delivery standard from bootstrap (L0) to operational maturity (L4). Each atom is the **unit of evidence at a single audit citation** — variants like `apply@local`, `test@battle`, `sync@migration` express scope without bloating the catalog.

```
code     (8)   ▶  format · lint · typing · test · security · license · sync · docs
data     (1)   ▶  seed
infra    (5)   ▶  install · build · publish · clean · help
ops      (7)   ▶  apply · destroy · monitor · logs · rollback · acceptance · backup
```

#### Domain × atom map

One-line semantics per atom. Variants are listed where the atom is canonically scoped.

| Domain | Atom | Capability | Common variants |
| --- | --- | --- | --- |
| **code** | `format` | code conforms to a deterministic style (zero diff on `--check`) | `format@<service>` |
| code | `lint` | static analysis catches anti-patterns and security smells | `lint@<service>` |
| code | `typing` | type system reports zero errors | `typing@<service>` |
| code | `test` | unit + integration tests pass | `test@cov`, `test@integration` |
| code | `security` | dependencies + code free of known CVEs | — |
| code | `license` | source headers + dependency licenses verified | — |
| code | `sync` | derived artifacts in sync with source-of-truth | `sync@migration`, `sync@types`, `sync@api`, `sync@state`, `sync@docs`, `sync@sbom` |
| code | `docs` | project documentation exists and is current | `docs@arch`, `docs@api`, `docs@runbook`, `docs@adr` |
| **data** | `seed` | development / test data hydration | `seed@minimal`, `seed@e2e`, `seed@demo` |
| **infra** | `install` | bootstraps a fresh checkout to runnable state | `install@dev` |
| infra | `build` | distributable artefacts produced (wheel, image, bundle) | `build@<service>`, `build@image` |
| infra | `publish` | artefacts uploaded to registry / store / CDN | `publish@test`, `publish@prod` |
| infra | `clean` | build artefacts and caches removable | `clean@db`, `clean@cache`, `clean@dist` |
| infra | `help` | Make surface self-documenting (`make help`) | — |
| **ops** | `apply` | drive runtime to declared state — local or env, idempotent | `apply@local`, `apply@<env>` |
| ops | `destroy` | remove runtime entirely — terminate processes or tear down env | `destroy@<env>` |
| ops | `monitor` | inspect current runtime state (health, metrics) | `monitor@<env>` |
| ops | `logs` | stream runtime events | `logs@<env>` |
| ops | `rollback` | revert deployed env to previous version | `rollback@<env>` |
| ops | `acceptance` | live system verification end-to-end | `acceptance@smoke`, `acceptance@e2e`, `acceptance@battle`, `acceptance@load`, `acceptance@chaos`, `acceptance@pen` |
| ops | `backup` | database + volume backups produced and restorable | `backup@<env>` |

#### Levels × atoms — cumulative ladder

Each level **strictly contains** the previous. A project advertises its `targetLevel` in `forktex.json`; `forktex fsd check` reports which atoms are required at that level and which still fail.

| Level | Name | Adds | Cumulative atoms |
| :---: | --- | --- | :---: |
| **L0** | Bootstrap | — | 0 |
| **L1** | Runnable | `install`, `apply`, `destroy`, `monitor`, `logs`, `build`, `publish`, `clean`, `help` | 9 |
| **L2** | Quality | `format`, `lint`, `typing`, `test`, `security`, `license`, `sync` | 16 |
| **L3** | Shippable | `docs` | 17 |
| **L4** | Operational | `acceptance`, `rollback`, `backup`, `seed` | 21 |

#### Variant syntax (`@`-qualifiers)

```
<atom>@<service>@<env>@<custom>...
```

Two **canonical biased axes** drive automatic Make-target generation:

- **`@<service>`** — drawn from `packages[*].name`; wraps recipe with `cd packages/<service>`
- **`@<env>`** — drawn from `cloud.environments[*].name`; injects `--env <env>` and sources `forktex.<env>.json` overlay

Anything else is **free-form** — `acceptance@battle`, `test@is-interesting`, `seed@minimal` — opaque pass-through, no injection. Combine freely: `apply@api@staging`, `build@web@image`, `acceptance@api@prod@chaos`. Canonical input order is service → env → custom; the parser accepts any order and normalises the Make-target name.

### 🧹  Lifecycle helpers

```bash
forktex status             # signed in? + project + Python + platform
forktex clean              # remove generated artifacts; forget projects that no longer exist
forktex clean --legacy-evidence   # also sweep historical timestamped FSD/arch outputs
```

---

## Three platforms · One CLI

Three platforms sit on the same shelf — each speaks the same `connect` / `disconnect` verbs, each lives at `forktex <platform> …`, each has a Python SDK, and each exposes an MCP endpoint at `/api/mcp` so AI assistants can read and write directly with the user's permissions.

<table>
<tr>
<td align="center" width="33%">
  <img src="https://cloud.forktex.com/assets/forktex-cloud-icon-BR2uDJyk.svg" height="64" alt="ForkTex Cloud"><br>
  <strong>cloud</strong><br>
  <sub>infra & deploys</sub>
</td>
<td align="center" width="33%">
  <img src="https://cloud.forktex.com/assets/forktex-intelligence-icon-COh1kdep.svg" height="64" alt="ForkTex Intelligence"><br>
  <strong>intelligence</strong><br>
  <sub>LLM, embeddings, search</sub>
</td>
<td align="center" width="33%">
  <img src="https://cloud.forktex.com/assets/forktex-network-icon-DKrK_c7g.svg" height="64" alt="ForkTex Network"><br>
  <strong>network</strong><br>
  <sub>identity, projects, channels</sub>
</td>
</tr>
<tr>
<td>

```bash
forktex cloud connect
forktex cloud up --env local
forktex cloud deploy <id>
```

Bring up local stacks; deploy from `forktex.json` to managed environments.

</td>
<td>

```bash
forktex intelligence connect
forktex intelligence ask  "..."
forktex intelligence run  "..."
```

LLM, embeddings, agentic runs.

</td>
<td>

```bash
forktex network connect
forktex network status
```

Identity, projects, tasks, worklogs.

</td>
</tr>
</table>

> 🧠 **Intelligence is what makes `forktex` chat smart.** The built-in agents above run with or without it; connect intelligence and bare `forktex` upgrades into a streaming chat REPL backed by an LLM. Cloud and network sit on the same level — connect any, all, or none.

### Three ways to reach a platform

```
       ╭──────────────╮     ╭──────────────╮     ╭──────────────╮
       │  ☁  cloud    │     │  🧠 intelligence │     │  🕸  network  │
       ╰──────┬───────╯     ╰──────┬───────╯     ╰──────┬───────╯
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
        ╭─────┴─────╮        ╭─────┴─────╮        ╭─────┴─────╮
        │  forktex  │        │ /api/mcp  │        │   pip /   │
        │    CLI    │        │   (MCP)   │        │    SDK    │
        ╰─────┬─────╯        ╰─────┬─────╯        ╰─────┬─────╯
              │                    │                    │
            you             AI assistants        your codebase
```

| | Path | One-liner |
|---|------|-----------|
| 💻 | **`forktex` CLI** | `forktex` drops you in. Fastest path for humans — chat, deploy, audit, all in one binary. |
| 🤖 | **MCP** (`/api/mcp`) | AI assistants read and write through Model Context Protocol with the credentials of the user who connected them. |
| 🔌 | **Python SDK** | `pip install forktex-cloud  ·  forktex-intelligence  ·  forktex-network` — same auth, same shapes. |

> Same data model on every path. A row created by an MCP-connected agent, a script using the SDK, and you typing `forktex network …` are indistinguishable to the platform.

---

## 60-second tour

```bash
# Built-in (no platform needed)
forktex agents root                            # ecosystem-aware local agent
forktex graph build                            # source-of-truth graph as JSON / DSL / HTML
forktex graph c4 --format html                 # drill-down C4 architecture view
forktex fsd check                              # delivery-standard audit

# Connect a platform (idempotent — login or register)
forktex intelligence connect
forktex cloud connect --api-key ftx-…
forktex network connect --endpoint http://localhost:9000 --email you@example.com

# Now the smart things light up
forktex                                        # bare → chat REPL (intelligence)
forktex intelligence ask "What does this project do?"
forktex cloud up --env local --build           # bring infra up from forktex.json
forktex serve                                  # live dashboard with the project graph
forktex status --json | jq '.intelligence.configured'
```

---

## Documentation

| Topic | Where |
|-------|-------|
| Full CLI reference (every verb, every slash command, every keybind) | [docs/cli-reference.md](docs/cli-reference.md) |
| Credentials — verbs, options, on-disk layout | [docs/credentials.md](docs/credentials.md) |
| Configuration — env vars, manifest, optional integrations | [docs/configuration.md](docs/configuration.md) |
| Development — `make ci`, `make quality`, license headers, install harness | [docs/development.md](docs/development.md) |
| Cloud SDK boundary contract — for SDK integrators | [docs/cloud-boundary.md](docs/cloud-boundary.md) |
| Security model — audit hook, structure spec, secret-tagged paths | [SECURITY.md](SECURITY.md) |
| Changelog — release notes per version | [CHANGELOG.md](CHANGELOG.md) |

---

## License

Dual-licensed — **AGPL-3.0-or-later** for open-source use, **commercial** for everything else (proprietary products, SaaS without source release, redistribution in closed-source form). See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for the full terms.

Commercial licensing inquiries: **info@forktex.com**.
