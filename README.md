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
# AI agent — interactive chat with tool calling
forktex

# AI agent — single question
forktex ask "What does this project do?"

# AI agent — orchestrated task
forktex run "Add error handling to src/app.py"

# Cloud — start local dev stack from forktex.json manifest
forktex cloud up --env dev --build

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
| **Intelligence** | AI agent with tool calling. Reads code, runs commands, applies patches. | `forktex chat`, `forktex ask`, `forktex run`, `forktex scrape` |
| **Cloud** | Deploy and manage infrastructure. Blue-green deploys from `forktex.json` manifests. | `forktex cloud up`, `forktex cloud deploy`, `forktex cloud server` |
| **FSD** | ForkTex Standard for Delivery. Verify compliance, generate ISO audit evidence. | `forktex fsd check`, `forktex fsd report` |

## CLI Commands

```
forktex                     Interactive AI chat (default)
forktex ask "..."           Single question
forktex run "..."           Orchestrated task

forktex cloud
  login                     Configure controller
  init                      Scaffold forktex.json
  up / down                 Start/stop stack
  deploy                    Blue-green deployment
  server list|create|show   Server management
  project list|create|show  Project management
  vault set|get|list        Secret management
  status / logs / events    Monitoring

forktex fsd
  check                     Verify FSD compliance
  report                    Run gates, generate evidence
  makefile sync             Generate Makefile from manifest

forktex arch discover       C4 architecture auto-discovery
forktex overview            Ecosystem overview
forktex git status-all      Multi-repo git operations
forktex scrape <url>        AI-driven web scraping
```

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

Settings are also read from `~/.forktex/` (global) and `.forktex/` (project-level) config files. Run `forktex intelligence init` and `forktex cloud login` to configure interactively.

## Development

```bash
# Editable install (pulls SDKs from PyPI)
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# Full ecosystem dev (editable SDKs from sibling repos)
pip install -e ../intelligence/sdk -e ../cloud/sdk -e ../core-py -e .[dev]

# Run tests
make test

# Regenerate Makefile from FSD manifest
forktex fsd --project-dir . makefile sync
```

## License

MIT
