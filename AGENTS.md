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
forktex fsd -d . makefile sync
forktex fsd -d . check
forktex fsd -d . report
forktex arch build -d .                  # graph.{json,dsl,html} + manual_bundle.json
forktex arch c4 --format html -d .
```

Only fall back to direct module execution when the CLI surface does not exist yet.

## Local Operator Loop

From repo root:

```bash
cd forktex-py
make install-global
forktex --version
forktex fsd -d . makefile sync
forktex fsd -d . check
forktex fsd -d . report
forktex arch build -d .                  # graph.{json,dsl,html} + manual_bundle.json
forktex arch c4 --format html -d .
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

- release line: `forktex` 0.8.0 (substrate + bucketed `.forktex/` + run-anywhere + cloud SDK 2.0; see `CHANGELOG.md`)
- FSD version: `1.3.0`
- profile: `package/python-library`
- achieved level: `L4`
- architecture packages: `forktex` (single-package repo — the four ecosystem SDKs live in their own repos and are installed as ordinary dependencies)
- key internal domains: `agent`, `core`, `graph`, `manual`, `fsd`, `manifest`, `models`, `runtime`, `substrate`, `scraper`
- `forktex.{cloud,intelligence,network}` are the **public re-export surface** for the SDKs (load-bearing — auth/chat/factories import through them), not thin shims
- `forktex.substrate` is the **sole filesystem authority**; the SDKs deal in pure data

Test + quality state: **532 unit tests green**, lint clean. Do not confuse
structural delivery capability with proof-clean execution — run
`forktex fsd report` for the live evidence pack.

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

`forktex arch build` is the canonical way to refresh the project graph;
`forktex arch c4` projects it onto the C4 model. The graph is the
single source of truth — agent tools, the dashboard, the C4 view, and the
agent-grounding `manual_bundle.json` all derive from one build, no duplicate
filesystem walks (`graph` + `manual` merged into `arch` in 0.8.0).

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

### SDK: `Cloud` is the only client name (forktex-cloud >= 2.0.0)

```python
from forktex_cloud import Cloud

with Cloud("https://cloud.forktex.com", account_key="ftx-...") as cloud:
    cloud.list_projects()
```

`Cloud` is the canonical (and only) SDK client class. forktex-cloud 2.0.0 is
**filesystem-free** (its `paths.py` was deleted — forktex-py's `substrate`
owns all on-disk layout; the SDK emits compose data). `Cloud.from_context(ctx)`
works the same.

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

## Recall — ground before you build

When you need to reorient inside this repo, **ground via the knowledge base
and the project graph before re-reading code** — and recycle non-obvious
decisions back so the next session inherits them. This is the dogfood loop:

```bash
# knowledge base — pinned standards + recycled project lessons (the doctrine)
forktex knowledge search "<topic>"     # search the composed fractal (docs ← global ← project)
forktex knowledge show <node-id>       # read one node in full
forktex knowledge doctor --composed    # cross-layer reference health

# project graph / architecture (built once via `forktex arch build -d .`)
forktex arch search "<topic>"          # ranked keyword search over nodes/edges
forktex arch c4 --format html          # C4 view of the same graph
```

When you reach a non-obvious decision, **recycle it** so it compounds across
sessions (this is how the knowledge base above stays useful):

```bash
forktex knowledge recycle <node-id> --title "…" --summary "…" --why "…" --how "…" [--tag pinned]
forktex knowledge recycle <node-id> --global     # host-wide / cross-project lesson (~/.forktex/knowledge)
```

The composed knowledge layers are `docs` (the engineering corpus) ← `global`
(`~/.forktex/knowledge`, cross-project) ← `project` (`<repo>/.forktex/knowledge`).
Pinned nodes are always injected into the chat agent's system prompt; everything
else is a pull-on-demand index. See `standard.knowledge-mechanism`.
