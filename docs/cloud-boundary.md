# forktex-py ↔ forktex-cloud SDK boundary

This document is the **integration contract** between forktex-py
(this repo) and the `forktex-cloud` SDK (separate PyPI package). It
captures who owns which side of every cross-package call so future
changes land on the right side of the line on the first try.

forktex-py depends on `forktex-cloud` as an ordinary PyPI dependency.
There is **no path-pinned cross-repo install**: this repo never
references `../cloud`. Every cross-repo change is a coordinated PR +
version bump on both sides.

## The five lanes

| Lane | What it is | Owner |
| --- | --- | --- |
| **A. Pure logic** | Computations, transforms, validators with no IO. Deterministic, easy to unit-test. | **SDK** |
| **B. Filesystem IO** | Reading and writing files anywhere on the user's machine — especially under `.forktex/`. | **forktex-py** via `forktex.graph.io_proxy.tracked_write` |
| **C. HTTP transport** | Talking to the hosted ForkTex Cloud API. | **SDK** (`forktex_cloud.client`, generated from the OpenAPI spec) — called from forktex-py's agent layer |
| **D. CLI orchestration** | Click groups, argv parsing, prompts, status spinners, exit codes, lifecycle hooks. | **forktex-py** (`src/forktex/agent/cloud/*`) |
| **E. Shared paths & conventions** | The on-disk shape of `.forktex/` and `~/.forktex/`. | **SDK** owns the canonical layout (`forktex_cloud.paths`); forktex-py re-exports + enforces the structure spec on top via `forktex.graph.structure` |

The mental shortcut: **logic + transport in the SDK, IO + UX in
forktex-py, paths defined once in the SDK and enforced once in forktex-py.**

## The audited bridge: `@sdk_boundary`

When forktex-py calls into the SDK and the SDK ends up writing under
`.forktex/`, that call is wrapped with
`forktex.runtime.decorators.sdk_boundary`. The decorator:

1. snapshots `.forktex/` before the call,
2. runs the SDK function,
3. snapshots `.forktex/` after,
4. validates the diff against `forktex.graph.structure`,
5. records each new/modified file in the registry under the SDK's
   writer name.

The SDK can be a black box for IO purposes, but every write it lands
inside `.forktex/` is still audited by the same structure spec that
gates `tracked_write`.

## Open follow-up: `scaffold_manifest`

`forktex_cloud.scaffold.templates.scaffold_manifest()` writes
`forktex.json` to disk directly via `target.write_text()`. Today this
works without complaint (the file is at the project root, not under
`.forktex/`, so the audit hook is correctly silent), but it's the
last on-disk write that originates inside the SDK rather than the
agent. The proper fix lives on the SDK side: split the function into

```python
def build_manifest_data(name: str, fsd_version: str | None = None) -> dict:
    """Pure: return the ready-to-serialise manifest dict."""
```

…and let forktex-py's `agent/cloud/init.py` call it then route the
write through `tracked_write`. ~10 LOC SDK + ~8 LOC agent.

## What stays SDK-side

- **`forktex_cloud.paths.global_dir()` / `project_dir()`** — these are
  *path constructors*, not IO.
- **`forktex_cloud.client.*`** — auto-generated from the OpenAPI
  spec.
- **`forktex_cloud.secrets.fernet`** — encryption + write of the
  Fernet vault. Splitting encryption from IO would buy little; the
  vault is small, security-critical, and well-isolated.

## What stays forktex-py-side

- **CLI prompts**, error messages, exit codes — Click is not in the
  SDK and shouldn't be.
- **Project-root resolution** (`forktex.core.paths.find_project_root`).
- **`tracked_write`, `tracked_append`, the audit hook, structure
  enforcement** — part of forktex-py's customer-facing contract
  about what lands in the user's working tree.
- **Lifecycle decorators** (`@needs_project`, `@long_running`,
  `@sdk_boundary`, `@tracked_writer`) — instance registry, heartbeat,
  signal handling.

---

## Inversion proposal — atom-layer dispatch

With the FSD v1.1.0 atom catalog in place, every cloud-side runtime
atom decomposes into a fixed **4-step pipeline**. The SDK / agent
boundary draws a single horizontal line through it:

```
                              SDK side                           Agent side
─────────────────────────────────────────────────────────────────────────────
1. PURE BUILD     forktex_cloud.bridge.local_compose
                    .build_compose_dict(manifest, env)         →  dict
                  forktex_cloud.scaffold.templates
                    .build_manifest_data(name, ...)            →  dict
                  forktex_cloud.bridge.persistence_defaults
                    .detect_persistence_defaults(manifest)     →  dict

2. PERSIST                                                     forktex.graph.io_proxy.tracked_write
                                                                 (.forktex/docker-compose.{env}.yml)
                                                                 (forktex.json at project root)

3. SUBSTRATE                                                   docker compose -f … up -d         (compose-local)
                                                                 DOCKER_HOST=ssh://… docker …    (docker-sandbox)
                                                                 ForktexCloudClient.deploy(…)   (managed)

4. VERIFY                                                      monitor@<env>      (healthcheck)
                                                                 acceptance@<env>   (e2e / smoke / battle)
─────────────────────────────────────────────────────────────────────────────
```

Step 1 is **pure**: no IO, no exceptions about filesystem state,
returns serialisable data. Steps 2–4 are **agent-owned**.

The atoms that flow through this pipeline are the ops-domain atoms —
`apply`, `destroy`, `monitor`, `logs`, `rollback`, `backup`,
`acceptance`. Each runs the same 4 steps, just substituting the
substrate at step 3.

### Concrete SDK split

Two SDK functions need promoting from internal to public, with the IO
half delegated to the agent:

| Today (SDK does IO) | After inversion (SDK pure + agent IO) |
| --- | --- |
| `bridge.local_compose.write_local_compose(manifest, root)` | `bridge.local_compose.build_compose_dict(manifest)` → agent calls `tracked_write` |
| `scaffold.templates.scaffold_manifest(root, name, ...)` | `scaffold.templates.build_manifest_data(name, ...)` → agent calls `tracked_write` |

Vault encryption stays where it is (security-critical, low ROI).

### Provider-axis dispatch

Each env in `cloud.environments[]` carries a `provider` field
(`compose-local` | `docker-sandbox` | `managed`). The agent's
`apply@<env>` recipe routes step 3 by that provider; the SDK sees the
same pure call regardless of where the workload lands.

```python
@translate_cloud_errors
@sdk_boundary(scope="project", project_root_arg="project_root")
async def apply_cmd(env: str, project_root: Path):
    manifest = load_manifest(project_root, env=env)
    provider = resolve_provider(manifest, env)

    if provider in ("compose-local", "docker-sandbox"):
        # 1. PURE BUILD
        compose = build_compose_dict(manifest)
        # 2. PERSIST
        compose_path = tracked_write(
            cloud_paths.compose_path(project_root, env),
            yaml.safe_dump(compose),
            kind="compose_export",
            writer="forktex.agent.cloud.apply",
        )
        # 3. SUBSTRATE
        run(["docker", "compose", "-f", compose_path, "up", "-d"],
            env=substrate_env(provider, env))

    elif provider == "managed":
        # 3. SUBSTRATE — controller is the source of truth
        async with ForktexCloudClient.from_context(ctx) as client:
            await client.deploy(env=env, manifest=manifest.to_cloud_payload())

    # 4. VERIFY
    await monitor_cmd(env=env, project_root=project_root)
```

### Coordinated multi-repo sequence

Order to land the inversion across repos:

1. **forktex-cloud SDK PR** — add `build_compose_dict()` and
   `build_manifest_data()` as public API alongside the existing IO
   functions; bump SDK minor version.
2. **forktex-py PR** — switch agent to the pure functions plus
   `tracked_write` directly. Constrain SDK dep range.
3. **forktex-cloud SDK PR (next minor)** — deprecate the old IO-bearing
   functions; remove on the following major.

This document is the contract. The execution follows.

---

## §X — Env-config model conflict (open)

forktex-py and the cloud SDK currently disagree on **how multiple
environments are declared**. Both models exist side-by-side in real
projects; intelligence and network both ship overlap today.

### The two models

**forktex-py model** (1.1.0): the project lists envs in a single
`forktex.json` file:

```jsonc
{
  "cloud": {
    "environments": [
      { "name": "local",      "provider": "compose-local" },
      { "name": "staging",    "provider": "managed"        },
      { "name": "production", "provider": "managed"        }
    ]
  }
}
```

This is what `cloud.environments[]` declared. The variant axis
(`apply@local`, `deploy@staging`, etc.) reads its allowed values
from this list.

**Cloud SDK model**: a base `forktex.json` plus separate per-env
overlay files, merged at load time:

```
forktex.json              # base / production
forktex.local.json        # overlay applied when --env local
forktex.staging.json      # overlay applied when --env staging
```

`forktex_cloud.manifest.loader.Manifest.load(path, env="local")` opens
`forktex.json` and (if it exists) deep-merges `forktex.local.json`
on top. The schema (`manifest/schema.py`) does **not** know about
`cloud.environments[]`. Service-level filtering uses
`services[].environments: list[str]` ("this service only runs in
these envs"); `Manifest.services_for_env(env)` walks that field.

### What intelligence has today

Both models present, partially overlapping:

| File | Shape | Env-related contents |
| --- | --- | --- |
| `forktex.json` | base manifest | declares `cloud.environments[] = [{name:"local",provider:"compose-local"},{name:"production",provider:"managed"}]` AND `cloud.metadata.environment = "production"` |
| `forktex.local.json` | overlay (cloud-SDK style) | overrides `cloud.metadata.environment = "local"` and replaces `cloud.services[]` with dev-port hot-reload variants |

When the user runs `forktex cloud up --env local`, the cloud SDK
loads the overlay and ignores `cloud.environments[]` in the base
manifest entirely. The `provider` field in `cloud.environments[]` is
**dead weight today** — nothing reads it.

### Concrete conflict points

1. **Source of truth for env names**: forktex-py says "the
   `environments[]` array enumerates them"; cloud SDK says "whatever
   `forktex.<env>.json` files exist on disk".
2. **Provider routing**: the planned 4-step pipeline (in the
   inversion proposal above) dispatches on
   `provider ∈ {compose-local, docker-sandbox, managed}`. That field
   only exists in forktex-py's model. The cloud SDK has no equivalent.
3. **Metadata vs registry**: `cloud.metadata.environment = "production"`
   in the base says "this manifest's default env is production".
   `cloud.environments[]` says "these are all envs". When they
   disagree (which they do in intelligence today), behaviour is
   undefined.
4. **Variant axis values**: `apply@local` and `deploy@staging` need
   to enumerate envs at Make-target generation time. Without
   `cloud.environments[]`, the generator would have to glob
   `forktex.*.json` on disk — fragile.
5. **Scaffold output**: `scaffold_manifest()` in the cloud SDK
   creates only `forktex.json`. Developers manually add
   `forktex.local.json`. forktex-py's model expects scaffold to
   produce the registry instead.

### Direction (locked separately, not in this slice)

The likely settlement: keep `cloud.environments[]` as the **registry**
(authoritative list of envs and their providers), and treat
`forktex.<env>.json` files as **optional populators** for one entry
in that registry. Either model alone is sufficient; both are
compatible. The cloud SDK's loader gains an `environments[]` walk;
the variant-axis generator reads from the registry.

This requires a coordinated cloud-SDK PR (out of scope for this
slice). Tracked as the follow-up to `scaffold_manifest()` inversion
above.

### Evidence collected during the loops

**Intelligence (2026-05-08, Loop 3)**: project carries both models simultaneously.

```
intelligence/forktex.json:
  manifestVersion: 1.1.0
  cloud.metadata.environment: "production"        # ← cloud-SDK selector
  cloud.environments[]: [
    { name: "local",      provider: "compose-local" },   # ← forktex-py registry
    { name: "production", provider: "managed"        }
  ]
  cloud.services[]: [ client, api, db, qdrant, redis, minio ]   # production-shape

intelligence/forktex.local.json:
  cloud.metadata.environment: "local"             # overrides the base
  cloud.services[]: [ client, api, worker, db, qdrant, redis, minio ]
                                                  # dev-port + hot-reload variants
```

When `forktex cloud up --env local` runs, the cloud SDK loader reads
`forktex.json`, deep-merges `forktex.local.json` on top, and produces
the local compose config. The `cloud.environments[]` block on the
base manifest is **never consulted**; the `provider: compose-local`
information is dropped on the floor.

**Network (2026-05-08, Loop 1)**: same shape — `forktex.json` declares
`cloud.environments[]` with three entries (`local`, `staging`,
`production`); `forktex.local.json` is the actually-consulted
overlay; staging/production envs have no overlay file but are
declared in the registry.

**Net**: the two models work today only because (a) developers
maintain both forms manually and (b) the `provider` field is unused
so its absence on the SDK side doesn't matter yet. Once the variant
parser starts dispatching on `provider`, the gap becomes load-bearing.

---

## §Y — Filesystem-ops responsibility audit

The "5-lane responsibility split" above says **forktex-py owns
filesystem IO**. In practice, the cloud SDK still does direct disk
writes at 11 sites. Each site is a candidate for inversion (move
the IO to forktex-py via `tracked_write`, leave the pure logic in
the SDK).

### Enumerated write sites (cloud SDK today)

| Path | Operation | SDK module | Inversion candidate |
| --- | --- | --- | --- |
| `.forktex/compose/docker-compose.<env>.yml` | YAML write | `bridge/local_compose.py:314` (`write_local_compose`) | **YES** — pure builder `build_compose_dict()` already proposed in inversion section |
| `.forktex/observability/{loki,promtail}.yml` | template copy | `bridge/local_compose.py:97-102` | YES — same proposal; copy templates from agent side |
| `.forktex/data/{service_id}/` | `mkdir` | `bridge/local_compose.py:259` | YES — agent owns directory creation under `.forktex/` |
| `.forktex/vault/<env>/secrets.enc` | encrypted JSON write | `secrets/fernet.py:77` | **HOLD** — security-critical; encryption + IO coupled. Low ROI to split |
| `forktex.json` (scaffold) | initial manifest write | `scaffold/templates.py:142` (`scaffold_manifest`) | YES — proposed `build_manifest_data()` split (covered in inversion section above) |
| `forktex.json` (re-save) | manifest write-back | `manifest/loader.py:363-365` | YES — agent should own the write; SDK returns the dict |
| `~/.forktex/cloud.json` | global context write | `ops.py:196` | YES — settings live in forktex-py's domain (`agent/cloud/settings.py`) |
| `.forktex/cloud.json` | project context write | `ops.py:203` | YES — same lane as global |
| `.forktex/` directory | scaffold + `.version` | `paths.py:206, 240` | partial — path constructor stays SDK; directory creation moves to agent |
| `.forktex/.gitignore` | append/create | `paths.py:252-254` | YES — `tracked_write` already handles structure-spec validation |

### Observation

Of 11 sites, **10 are inversion candidates** and **1 stays
SDK-owned** (vault encryption — security-critical, tightly coupled).
The full inversion is multi-PR coordinated work; the
`scaffold_manifest()` and `write_local_compose()` splits already in
the inversion proposal cover the two highest-traffic sites.

### Audit lane mechanism

When a write is moved to forktex-py:

1. Pure builder lives in the SDK, takes data, returns a dict / bytes.
2. forktex-py's `agent/cloud/<x>.py` calls the builder, then
   `forktex.graph.io_proxy.tracked_write(path, content, kind=...,
   writer="forktex.agent.cloud.<x>")`.
3. `tracked_write` validates the path against
   `forktex.graph.structure` (the canonical `.forktex/` spec) and
   records the touch in the registry.
4. Optionally wrap the builder call site in
   `@forktex.runtime.decorators.sdk_boundary` for an extra audit
   snapshot — though once the IO is forktex-py's, the boundary
   wrapper adds no new safety.

### Evidence collected during the loops

Loop 3 (graph build against intelligence) surfaced no new SDK-side
write sites — graph build is forktex-py-only. Loop 2 (which would
exercise `forktex cloud up`, `down`, `monitor` against the live
stack) is the next opportunity to capture concrete write-site
evidence; deferred until a Docker daemon is available.

---

## Loop findings (forktex-py-side)

Side-channel notes from running the iteration loops against
intelligence and network. These are forktex-py issues / gaps
distinct from the cloud-boundary conflicts above.

### Loop 1 — `make ci` smoke

- **`make ci` was missing from intelligence + network** after the
  org-side prune cycle (the standard's `ci` chord requires
  `format-check` as a render dependency, which doesn't auto-render
  for sub-package-only repos). **Fixed** in both projects'
  `forktex.json` by restoring a workspace-level `ci` override that
  recurses into each package's per-package `ci` target. Generator
  gap candidate: emit `format-check` as a workspace-level recursive
  secondary when subpaths exist (today it's only emitted for
  root-level Python).
- **`make -C sdk-py ci` from intelligence passes end-to-end**
  (format-check + lint + typecheck + test + audit + license-check
  + wheel build + twine check + verify_wheel_import). Confirms the
  shared per-package ci pattern works.

### Loop 3 — graph + AGENTS.md context

- **Graph walker stopped at top-level modules per domain**. Real
  projects nest substructure (`api/src/ai/chat/orchestrator.py`).
  **Fixed** in `forktex.graph.build._modules_under` (commit `3bd9e9f`):
  recursive `rglob('*.py')` with `SKIP_DIRS` guard; dotted names
  rebuilt from the path-relative-to-`src_dir`. Smoke against
  intelligence: 180→277 nodes, 581→988 edges, ai/* modules 3→23.
- **`forktex agents ground` has no refresh action**. Today the
  command exposes only `repos` (list) and `status` (display) — no
  way to actually regenerate AGENTS.md from the graph + manifest.
  The Phase-1 audit described `--all` and `--status` flags but the
  CLI surface ships neither write subcommand. **Open**: add
  `forktex agents ground refresh` (or `apply`) that walks the
  workspace, renders per-project AGENTS.md from the graph + the
  project's `forktex.json`. Out of scope this slice.

### Loop 4 — agent-driven dev ops (graph CLI shortcuts)

All five graph CLI shortcuts verified against intelligence:

- `forktex graph package <path>` — correct package metadata for
  `sdk-py`, `api`, `client`.
- `forktex graph modules <pattern>` — finds nested modules
  (`orchestrator` resolves to `api/src/ai/chat/orchestrator.py`).
- `forktex graph importers <target>` — `pydantic` resolves to 8
  importers across api + sdk-py; `httpx` to 1.
- `forktex graph recent --hours N` — surfaces fsd evidence + instance
  registry writes.
- `forktex graph ecosystem` — tree view of 12 registered projects.

The remaining 7 graph tools (`graph_summary`, `list_packages`,
`find_package`, `list_domains`, `list_modules_in_domain`,
`fsd_status`, `validate_path`, `ecosystem_matrix`) live only in the
agent's `IntelligenceToolServer` — not exposed as standalone CLI
shortcuts. **Open**: agent-driven verification (running an actual
LLM session over intelligence's repo) requires the Intelligence
SDK to be reachable; deferred until a connected agent loop is
available.

