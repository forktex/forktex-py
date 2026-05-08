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
