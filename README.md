# forktex

[![PyPI](https://img.shields.io/pypi/v/forktex.svg)](https://pypi.org/project/forktex/)
[![Python](https://img.shields.io/pypi/pyversions/forktex.svg)](https://pypi.org/project/forktex/)
[![License](https://img.shields.io/pypi/l/forktex.svg)](https://github.com/forktex/forktex-py/blob/master/LICENSE)

AI-powered development toolkit: agent, cloud infrastructure, delivery standard enforcement, and architecture discovery in a single `forktex` command.

## Install

**One-liner** (Linux / macOS):

```bash
curl -sSL install.forktex.com/sh | sh
```

**One-liner** (Windows, PowerShell 5.1+):

```powershell
iwr -useb install.forktex.com/ps | iex
```

The installer detects Python ≥ 3.12, prefers `pipx` (isolated install), falls back to `pip --user`, and seeds `~/.forktex/` (POSIX) or `%APPDATA%/forktex/` (Windows) automatically. If your system Python is older it prints OS-specific install hints (deadsnakes, brew, winget, dnf).

**Manual**:

```bash
pipx install forktex             # recommended — isolates deps
# or
pip install --user forktex
# Optional: web scraping support (Playwright)
pipx install forktex[web] && playwright install
```

**Requires Python 3.12+.** Tested on 3.12, 3.13, 3.14. Covers Ubuntu 24.04 LTS, Fedora 41+, Homebrew Python on macOS, and Windows 3.12+. Debian 12 stable users on system Python need `apt install -t bookworm-backports python3.12` or deadsnakes.

## Quick Start

```bash
# AI agent — interactive chat with tool calling (bare forktex drops you in)
forktex

# AI agent — single-shot question (scriptable)
forktex intelligence ask "What does this project do?"

# AI agent — orchestrated task
forktex intelligence run "Add error handling to src/app.py"

# Cloud — start local stack from forktex.json manifest
forktex cloud up --env local --build

# Cloud — deploy to production
forktex cloud deploy <server-id>

# FSD — check delivery standard compliance
forktex fsd check

# FSD — generate ISO audit evidence
forktex fsd report
```

## Pillars

| Pillar | What it does | Key commands |
|--------|-------------|--------------|
| **Intelligence** | AI agent with tool calling. Reads code, runs commands, applies patches. | `forktex` (chat), `forktex intelligence ask/run/scrape` |
| **Cloud** | Deploy and manage infrastructure. Blue-green deploys from `forktex.json` manifests. | `forktex cloud up`, `forktex cloud deploy`, `forktex cloud server` |
| **Network** | Identity, projects, tasks, worklogs, channels. | `forktex network connect`, `forktex network status` |
| **FSD** | ForkTex Standard for Delivery. Verify compliance, generate ISO audit evidence. | `forktex fsd check`, `forktex fsd report` |

The bare `forktex` menu shows each service in its brand colour with a terminal-native ASCII rendering of its mark — cloud as a full 8-arm radial, intelligence as a head-with-body, network as a diagonal X.

## CLI Commands

Three services — **cloud**, **intelligence**, **network** — sit at the same level in the command tree. Each exposes its own operations plus the identical credential pair `connect` / `disconnect`. A top-level `forktex status` aggregates credential state across all three.

```
forktex                      Bare: menu-driven root loop (auto-upgrades to chat)
forktex status               Aggregate credential state (cloud + intelligence + network)
forktex info                 Project + environment summary

forktex cloud
  connect / disconnect       Authenticate / remove credentials
  init                       Scaffold forktex.json manifest
  up / down                  Start / stop stack
  deploy                     Blue-green deployment
  server | project | vault   Per-resource subgroups
  status / logs / events     Monitoring

forktex intelligence
  connect / disconnect       Authenticate / remove credentials
  status                     API health + whoami
  ask "..."                  Single-shot question
  run "..."                  Orchestrated task
  scrape <url>               Agentic browser scraper
  index-ecosystem            Knowledge ingestion

forktex network
  connect / disconnect       Authenticate / remove credentials
  status                     identity_me round-trip

forktex fsd                  Delivery-standard checks + ISO evidence
forktex arch discover        C4 auto-discovery
forktex overview             Ecosystem overview
forktex git status-all       Multi-repo git operations
```

## Chat REPL

Bare `forktex` opens the menu; if intelligence is reachable, pressing Enter drops you into the chat REPL (a full-screen `prompt_toolkit` app).

**Slash commands** (type `/` for a live dropdown; Tab accepts):

```
/help          show this list
/status        aggregate credential state
/connect       <service> [--new]   idempotent login-or-register
/disconnect    <service>           remove saved credentials
/cards         toggle service cards (hidden by default)
/clear         clear visible buffer
/history       show full transcript
/tools         list local tool-server tools
/menu          exit chat back to menu
/quit          exit forktex
```

**Keybindings (quick-casts)**:

```
Ctrl+K   toggle service cards                Ctrl+L   clear visible buffer
Ctrl+H   show full transcript                Ctrl+D   exit to menu
Tab      autocomplete slash / service        Enter    submit
```

**Menu keys (pre-chat)**: `c` / `i` / `n` drill into service help, `s` status, `r` refresh probes, `h` hide cards, `q` quit, `Enter` → chat (when intelligence reachable). Typing `/` opens the same live dropdown as in chat.

## Credentials — one verb, three services

```bash
forktex status                                              # aggregate table (all 3 services)
forktex cloud connect                                       # email/password + org select (or --api-key ftx-…)
forktex intelligence connect                                # idempotent: login or register, then issue key
forktex intelligence connect --new                          # force register
forktex network connect --endpoint http://localhost:9000 \
                        --email you@example.com
forktex <service> disconnect [--global]                     # remove saved creds
```

Every service understands the same option set: `--endpoint`/`--url`, `--email`, `--password`, `--api-key`, `--global`, `--new`. Credentials live at `~/.forktex/{cloud,intelligence,network}.json` (global) or `<project>/.forktex/…` (per-project). See the [forktex directory spec](https://github.com/forktex/cloud/blob/master/docs/forktex-directory-spec.md).

## Ecosystem

```
forktex-core             Shared PostgreSQL/Redis primitives
forktex-cloud            Cloud platform SDK (httpx client)
forktex-intelligence     Intelligence API SDK (LLM, embeddings, search)
forktex-network          Network platform SDK (identity, projects, channels)
      |        |        |        |
      +--------+--------+--------+
                       |
                  forktex          CLI + agent + FSD (this package)
```

Each SDK is independently versioned and published to PyPI. `forktex` re-exports their surfaces under `forktex.cloud`, `forktex.intelligence`, and `forktex.network` as convenience shims.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `FORKTEX_INTELLIGENCE_ENDPOINT` | Intelligence API endpoint | `https://intelligence.forktex.com/api` |
| `FORKTEX_INTELLIGENCE_API_KEY` | Intelligence API key | *(required for AI features)* |
| `FORKTEX_DEBUG` | Enable debug output | `false` |

Settings are also read from `~/.forktex/` (global) and `.forktex/` (project-level) config files. Run `forktex <service> connect` to configure each service interactively.

The full on-disk layout — every file under `.forktex/` and `~/.forktex/`, what writes it, whether it's gitignored — is defined by the [forktex directory spec](https://github.com/forktex/cloud/blob/master/docs/forktex-directory-spec.md) and enforced in code via `forktex_cloud.paths`.

## Development

```bash
# Editable install with the dev group (pytest, ruff, pyright, pip-audit, respx)
poetry install --with dev

# Run tests
make test

# Run the full publish gate (format-check + lint + license-check + audit + test + build)
make ci

# Regenerate Makefile from forktex.json
forktex fsd makefile sync
```

`make ci` is the single command that gates a publish: it format-checks, lints, verifies dual-license headers across every source file, audits dependencies for known CVEs, runs the test suite, and builds the wheel + sdist with `twine check` — finishing with a *"safe to: make publish-test  /  make publish"* banner. The same chain runs in GitHub Actions on every push and PR across Python 3.12 / 3.13 / 3.14.

### License headers

Every source file carries the AGPL-3.0 + Commercial dual-license SPDX header, applied idempotently via:

```bash
make license-check    # CI gate — fails if any source file is missing the header
make license-fix      # add or refresh headers across src/, tests/, scripts/
make license-strip    # remove headers (used before license-model changes)
```

### Developing against sibling SDK checkouts

Swap the installed `forktex-cloud`, `forktex-intelligence`, and `forktex-network` with editable installs from `../cloud/sdk-py`, `../intelligence/sdk-py`, `../network/sdk-py`:

```bash
make dev-link-sdks              # editable from siblings
export FORKTEX_DEV_SIBLING_SDKS=1   # adds "(dev-linked)" to `forktex --version`
# …iterate on SDK sources — imports pick up changes without a reinstall…
make dev-unlink-sdks            # restore pinned PyPI versions
```

## License

Dual-licensed — **AGPL-3.0-or-later** for open-source use, **commercial** for everything else (proprietary products, SaaS without source release, redistribution in closed-source form). See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for the full terms.

Commercial licensing inquiries: info@forktex.com.

The 1.0.0 release on PyPI remains under MIT; from **1.0.1** onwards the package ships AGPL-3.0+Commercial.
