# forktex

[![PyPI](https://img.shields.io/pypi/v/forktex.svg)](https://pypi.org/project/forktex/)
[![Python](https://img.shields.io/pypi/pyversions/forktex.svg)](https://pypi.org/project/forktex/)
[![License](https://img.shields.io/pypi/l/forktex.svg)](https://github.com/forktex/forktex-python/blob/master/LICENSE)

AI-powered development toolkit: agent, cloud infrastructure, delivery standard enforcement, and architecture discovery in a single `forktex` command.

## Install

```bash
pip install forktex

# Optional: web scraping support (Playwright)
pip install forktex[web]
playwright install
```

Requires Python 3.11+.

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

## Three Pillars

| Pillar | What it does | Key commands |
|--------|-------------|--------------|
| **Intelligence** | AI agent with tool calling. Reads code, runs commands, applies patches. | `forktex` (chat), `forktex intelligence ask/run/scrape` |
| **Cloud** | Deploy and manage infrastructure. Blue-green deploys from `forktex.json` manifests. | `forktex cloud up`, `forktex cloud deploy`, `forktex cloud server` |
| **Network** | Identity, projects, tasks, worklogs, channels. | `forktex network login`, `forktex network status` |
| **FSD** | ForkTex Standard for Delivery. Verify compliance, generate ISO audit evidence. | `forktex fsd check`, `forktex fsd report` |

## CLI Commands

The three facets — **cloud**, **intelligence**, **network** — sit at the same level in the command tree. Each exposes its own operations plus the identical credential pair `login` / `logout`. A top-level `forktex status` aggregates credential state across all three.

```
forktex                      Bare: menu-driven root loop (auto-upgrades to chat)
forktex status               Aggregate credential state (cloud + intelligence + network)
forktex info                 Project + environment summary

forktex cloud
  login / logout             Authenticate / remove credentials
  init                       Scaffold forktex.json manifest
  up / down                  Start / stop stack
  deploy                     Blue-green deployment
  server | project | vault   Per-resource subgroups
  status / logs / events     Monitoring

forktex intelligence
  login / logout             Authenticate / remove credentials
  status                     API health + whoami
  ask "..."                  Single-shot question
  run "..."                  Orchestrated task
  scrape <url>               Agentic browser scraper
  index-ecosystem            Knowledge ingestion

forktex network
  login / logout             Authenticate / remove credentials
  status                     identity_me round-trip

forktex fsd                  Delivery-standard checks + ISO evidence
forktex arch discover        C4 auto-discovery
forktex overview             Ecosystem overview
forktex git status-all       Multi-repo git operations
```

## Credentials — one verb, three facets

```bash
forktex status                                              # aggregate table (all 3 facets)
forktex cloud login                                         # email/password + org select (or --api-key ftx-…)
forktex intelligence login                                  # login-or-register + key issue
forktex network login --endpoint http://localhost:9000 \
                     --email you@example.com
forktex <facet> logout [--global]                           # remove saved creds
```

Every facet understands the same option set: `--endpoint`/`--url`, `--email`, `--password`, `--api-key`, `--global`, `--new-account`. Credentials live at `~/.forktex/{cloud,intelligence,network}.json` (global) or `<project>/.forktex/…` (per-project). See the [forktex directory spec](https://github.com/forktex/cloud/blob/master/docs/forktex-directory-spec.md).

## Ecosystem

```
forktex-core             Shared PostgreSQL/Redis primitives
forktex-cloud            Cloud platform SDK (httpx client)
forktex-intelligence     Intelligence API SDK (LLM, embeddings, search)
      |                          |
      +----------+---------------+
                 |
            forktex              CLI + agent + FSD (this package)
```

Each SDK is independently versioned and published to PyPI. `forktex` re-exports their surfaces under `forktex.cloud` and `forktex.intelligence` as convenience shims.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `FORKTEX_INTELLIGENCE_ENDPOINT` | Intelligence API endpoint | `https://intelligence.forktex.com/api` |
| `FORKTEX_INTELLIGENCE_API_KEY` | Intelligence API key | *(required for AI features)* |
| `FORKTEX_DEBUG` | Enable debug output | `false` |

Settings are also read from `~/.forktex/` (global) and `.forktex/` (project-level) config files. Run `forktex <facet> login` to configure each facet interactively.

The full on-disk layout — every file under `.forktex/` and `~/.forktex/`, what writes it, whether it's gitignored — is defined by the [forktex directory spec](https://github.com/forktex/cloud/blob/master/docs/forktex-directory-spec.md) and enforced in code via `forktex_cloud.paths`.

## Development

```bash
# Editable install (pulls forktex-cloud and forktex-intelligence from PyPI)
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# Run tests
make test

# Regenerate Makefile from FSD manifest
forktex fsd --project-dir . makefile sync
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

MIT
