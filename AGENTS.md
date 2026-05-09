# Forktex Agent Guide

This repo should be operated through `forktex` itself as much as possible.

## First Principles

- `forktex.json` is the project contract
- `manifestVersion` versions the manifest shape
- `fsd.version` versions the active delivery contract
- `cloud.apiVersion` versions cloud-only deployment manifests
- the root `Makefile` is generated, not primary
- the canonical runtime-control atoms are `apply`, `destroy`, `monitor` (declared by workspace projects; forktex-py itself uses `package/python-library` and disables them)

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
make gate            # pre-merge quality chord (renamed from `ci`)
make acceptance      # wheel install + CLI battle-test
make manual          # generate the architecture + AI context manual
make format-check
make lint
make test
make build
```

## Current Reality

The repo currently self-assesses as:

- FSD version: `1.2.0`
- profile: `package/python-library`
- achieved level: `L4`
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

## Cloud SDK & Workspace Atoms (heads-up for parallel agents)

The `forktex-cloud` SDK and the `cloud/` repo layout both moved a step
forward — relevant when this repo's CLI talks to the controller.

### SDK: prefer `Cloud` (forktex-cloud >= 0.2.5)

```python
from forktex_cloud import Cloud

with Cloud("https://cloud.forktex.com", account_key="ftx-...") as cloud:
    cloud.list_projects()
```

`ForktexCloudClient` remains exported as the long-form alias (`Cloud is
ForktexCloudClient`), so every existing import in `src/forktex/agent/cloud/*`
keeps working untouched. New code should use `Cloud`. The constructor
signature is unchanged: `(base_url, account_key=None, *, access_token=None,
org_id=None, timeout=30.0)`. `Cloud.from_context(ctx)` works the same.

### Cloud repo: directory-per-VPS layout (in flight)

The cloud repo is migrating to a symmetric directory-per-VPS layout
(`cloud/backup/`, `cloud/registry/`, `cloud/code/`, `cloud/provider/`,
each with its own `forktex.json` + own optional Makefile via `forktex fsd
makefile sync`). The controller still lives at `cloud/api/` for now;
Phase 3 of the migration moves it into `cloud/controller/`.

Workspace atoms exposed at the root `cloud/Makefile` use the
`<verb>@<instance>` convention (matches systemd / Docker idiom; chosen
because it scales as more verbs land — `destroy@*`, `logs@*`, etc.):

| Atom | What it does |
|---|---|
| `make apply@backup` | `cd backup && forktex cloud up --env $FORKTEX_ENV` (default `production`) |
| `make apply@registry` | same shape, `cloud/registry/` |
| `make apply@code` | same shape, `cloud/code/` |
| `make apply@provider` | same shape, `cloud/provider/` (stub manifest until DockerProvider Phase 1B) |
| `make ci@backup` | delegates to `cloud/backup/`'s own `make ci` (format-check + lint + pytest) |
| `make ci-all` | aggregate CI: ci-fast + ci-api + ci-client + ci@backup + per-subsystem config sanity |
| `make deps-all` | install deps for every subsystem |

Flat verb names (`ci-fast`, `ci-api`, `ci-all`, `deps-all`,
`deps`) are kept where the verb isn't parametric. Legacy
`make deploy-{dev,staging,production}` (controller deploy via env
overlay) is unchanged — operator runbook compat. Only the new
per-subsystem atoms use the `<verb>@<instance>` form.

VPN currently lives inside the controller (`cloud/api/src/vpn/`); no
VPS extraction planned yet — promote when there's a real reason to
separate it.
