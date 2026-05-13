# Configuration

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FORKTEX_INTELLIGENCE_ENDPOINT` | Intelligence API endpoint | `https://intelligence.forktex.com/api` |
| `FORKTEX_INTELLIGENCE_API_KEY`  | Intelligence API key | *(required for AI features)* |
| `FORKTEX_DEBUG`                 | Enable debug output | `false` |
| `FORKTEX_DEV_SIBLING_SDKS`      | Append `(dev-linked)` to `forktex --version` | unset |

Settings are also read from `~/.forktex/` (global) and `<project>/.forktex/` (project-level) config files. Run `forktex <service> connect` to configure a service interactively.

## On-disk layout

The full layout — every file under `.forktex/` and `~/.forktex/`, what writes it, whether it's gitignored — is enforced by the structure spec at `forktex.graph.structure`. Path constants live in `forktex_cloud.paths` (the SDK) and are re-exported by `forktex.graph.io_proxy`.

## Manifest — `forktex.json`

The manifest is the source of truth for project metadata, FSD profile, atom overrides (the recipe behind every Make target), and (when the cloud SDK is connected) deployment composition. `forktex fsd makefile sync` regenerates the Makefile from the atoms.

## Optional integrations

`forktex` is a generic software-tooling library on its own. Three optional integrations bolt on through their own SDKs — each `pip install`able alone, each connected with `forktex <name> connect`:

| Integration | What it adds | SDK package |
| --- | --- | --- |
| **cloud** | environment lifecycle (`apply`, `destroy`, `monitor`, deploy) | `forktex-cloud` |
| **intelligence** | LLM, embeddings, agentic runs | `forktex-intelligence` |
| **network** | identity, projects, tasks, worklogs | `forktex-network` |

Each SDK is independently versioned and published to PyPI. `forktex` re-exports the SDK surfaces under `forktex.cloud`, `forktex.intelligence`, and `forktex.network` as convenience shims so app code can `from forktex.intelligence import …` instead of pinning the SDK directly.

## Brand assets

The canonical brand SVGs (banners + icons for `forktex`, `forktex-cloud`, `forktex-intelligence`, `forktex-network`) are hosted at **`https://forktex.com/forktex-assets/`** — e.g. `forktex-cloud-icon.svg`, `forktex-intelligence-banner.svg`. Use them in your own dashboards, READMEs, and integration docs.
