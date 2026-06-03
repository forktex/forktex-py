# Configuration

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FORKTEX_INTELLIGENCE_ENDPOINT` | Intelligence API endpoint | `https://intelligence.forktex.com/api` |
| `FORKTEX_INTELLIGENCE_API_KEY`  | Intelligence API key | *(required for AI features)* |
| `FORKTEX_DEBUG`                 | Enable debug output | `false` |
| `FORKTEX_DEV_SIBLING_SDKS`      | Append `(dev-linked)` to `forktex --version` | unset |

Settings are also read from `~/.forktex/` (global) and `<project>/.forktex/` (project-level) config files. Run `forktex <service> connect` to configure a service interactively.

## On-disk layout — `.forktex/`, bucketed by lifecycle

forktex-py is the **sole filesystem authority** — `forktex.substrate` owns every
path under `.forktex/` and `~/.forktex/`; the SDKs (cloud/intelligence/network)
deal in pure data and never touch disk. The layout is organized **by lifecycle,
not by feature**, at both project and OS scope:

| Bucket | Holds | Rule |
| --- | --- | --- |
| `knowledge/` | recycled lessons, notes | the only thing you commit |
| `secrets/` | creds, vault, keys, `.env` | never commit, never share |
| `cache/` | graph, c4, manual bundle, compose, fsd evidence | delete = rebuild |
| `state/` | instances, locks | ephemeral |
| `.version`, `.gitignore`, `config.json` | markers + config | — |

Path factories live in `forktex.substrate.paths`; the full spec (every file,
what writes it, whether it's gitignored) is the `EntrySpec` set in
`forktex.substrate.spec`, audited by `forktex arch audit`. Writes go through
`forktex.graph.io_proxy.tracked_write` so attribution + permissions are
enforced. See `standard.forktex-fingerprint` + `standard.forktex-architecture`.

## Manifest — `forktex.json`

The manifest is the source of truth for project metadata, FSD profile, atom overrides (the recipe behind every Make target), and (when the cloud SDK is connected) deployment composition. `forktex fsd makefile sync` regenerates the Makefile from the atoms.

## Optional integrations

`forktex` is a generic software-tooling library on its own. Three optional integrations bolt on through their own SDKs — each `pip install`able alone, each connected with `forktex <name> connect`:

| Integration | What it adds | SDK package |
| --- | --- | --- |
| **cloud** | environment lifecycle (`apply`, `destroy`, `monitor`, deploy) | `forktex-cloud` |
| **intelligence** | LLM, embeddings, agentic runs | `forktex-intelligence` |
| **network** | identity, projects, tasks, worklogs | `forktex-network` |

Each SDK is independently versioned and published to PyPI. `forktex` re-exports the SDK surfaces under `forktex.cloud`, `forktex.intelligence`, and `forktex.network` — the load-bearing public import surface (auth flows, chat, and client factories all import through them), so app code can `from forktex.intelligence import …` instead of pinning the SDK directly.

## Brand assets

The canonical brand SVGs (banners + icons for `forktex`, `forktex-cloud`, `forktex-intelligence`, `forktex-network`) are hosted at **`https://forktex.com/forktex-assets/`** — e.g. `forktex-cloud-icon.svg`, `forktex-intelligence-banner.svg`. Use them in your own dashboards, READMEs, and integration docs.
