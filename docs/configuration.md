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

The full layout — every file under `.forktex/` and `~/.forktex/`, what writes it, whether it's gitignored — is defined by the [forktex directory spec](https://github.com/forktex/cloud/blob/master/docs/forktex-directory-spec.md) and enforced in code via `forktex_cloud.paths`.

## Manifest — `forktex.json`

The manifest is the source of truth for project metadata, FSD profile, atoms (CI/test/build commands), and cloud stack composition. `forktex fsd makefile sync` regenerates the Makefile from the atoms; `forktex cloud up` reads the same manifest to bring up local infra.

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

Each SDK is independently versioned and published to PyPI. `forktex` re-exports their surfaces under `forktex.cloud`, `forktex.intelligence`, and `forktex.network` as convenience shims so app code can `from forktex.intelligence import …` instead of pinning the SDK directly.

## Brand assets

The canonical brand SVGs (banners + icons for `forktex`, `forktex-cloud`, `forktex-intelligence`, `forktex-network`) are hosted at **`https://forktex.com/forktex-assets/`** — e.g. `forktex-cloud-icon.svg`, `forktex-intelligence-banner.svg`. Use them in your own dashboards, READMEs, and integration docs.
