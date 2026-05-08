# Forktex Agent Guide

This repo should be operated through `forktex` itself as much as possible.

## First Principles

- `forktex.json` is the project contract
- `manifestVersion` versions the manifest shape
- `fsd.version` versions the active delivery contract
- `cloud.apiVersion` versions cloud-only deployment manifests
- the root `Makefile` is generated, not primary
- the canonical runtime-control atoms are `start`, `stop`, `logs`

## Preferred Control Surface

Use the globally installed editable CLI whenever possible:

```bash
forktex --version
forktex fsd --project-dir . makefile sync
forktex fsd --project-dir . check --json-output
forktex fsd --project-dir . report
forktex graph build --project .          # writes graph.{json,dsl,html}
forktex graph c4 --format html --project .
```

Only fall back to direct module execution when the CLI surface does not exist yet.

## Local Operator Loop

From repo root:

```bash
cd forktex-py
make install-global
forktex --version
forktex fsd --project-dir . makefile sync
forktex fsd --project-dir . check
forktex fsd --project-dir . report
forktex graph build --project .          # writes graph.{json,dsl,html}
forktex graph c4 --format html --project .
```

Useful Make targets:

```bash
make help
make start
make stop
make logs
make format-check
make lint
make test
make build
```

## Current Reality

The repo currently self-assesses as:

- FSD version: `1.0.0`
- achieved level: `L3`
- architecture packages: `forktex` (single-package repo — the four ecosystem SDKs live in their own repos and are installed as ordinary dependencies)
- key internal domains: `agent`, `architecture`, `cloud` (shim), `core`, `engineering`, `filesystem`, `fsd`, `intelligence` (shim), `manifest`, `models`

Current proof failures from `forktex fsd report`:

- formatting drift across many Python files
- lint debt, especially unused imports in tests
- `tests/test_cloud_client.py` depends on an external cloud API app import path and fails in this repo alone

So:

- `forktex fsd check` passes at `L3`
- `forktex fsd report` still fails

Do not confuse structural delivery capability with proof-clean execution.

## When Editing The Delivery Surface

If you need to change the generated Makefile behavior, prefer this order:

1. update the bundled FSD standard
2. update profiles
3. update `forktex.json`
4. update generator logic
5. regenerate with `forktex fsd makefile sync`

Do not hand-edit the root `Makefile` as the source of truth.

## Manifest Notes

General-purpose project fields belong at manifest root:

- `manifestVersion`
- `name`
- `version`
- `description`
- `packages`
- `fsd`

Cloud deployment-specific fields belong under `cloud`.

Backward compatibility still exists for older top-level cloud fields, but new work should write nested `cloud`.

## Architecture Notes

`forktex graph build` is the canonical way to refresh the project graph;
`forktex graph c4` projects it onto the C4 model. The graph is the
single source of truth — agent tools, the dashboard, and the C4 view
all read from it, no duplicate filesystem walks.

For `forktex-py`, the graph exposes both:

- publishable package nodes
- internal domain nodes derived from `src/forktex/*`
- AST-extracted import edges (when `--imports` is on, the default)

If the graph and FSD output disagree, treat that as a product bug and
fix the toolchain rather than documenting around it. After
`forktex fsd check`, the FSD level is stamped onto the package node so
the C4 view reflects the latest evaluation.
