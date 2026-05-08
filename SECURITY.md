# Security

This document covers ForkTex's local security posture and the hardening
recommendations we ship with for going live in customer environments.
For vulnerability disclosure see [Reporting](#reporting) at the bottom.

---

## Threat model

ForkTex runs as a developer-machine CLI. The trust boundary is **the
local user account**. Inside that boundary we consider:

| Asset | Where it lives | Sensitivity |
|---|---|---|
| Cloud auth token + account key | `~/.forktex/cloud.json` | secret |
| Intelligence API key | `~/.forktex/intelligence.json`, project mirror | secret |
| Network JWT | `~/.forktex/network.json`, project mirror | secret |
| Per-project encrypted vault | `<root>/.forktex/vault/{env}/secrets.enc` | secret (Fernet) |
| SSH private keys | `<root>/.forktex/state/keys/*.key` | secret |
| DB backups (`pg_dump.gz`) | `<root>/.forktex/backups/{ts}/*.sql.gz` | secret |
| Project graph + C4 exports | `<root>/.forktex/graph.{json,dsl,html}`, `c4.html` | public |
| Live instance records | `~/.forktex/instances/<run_id>.json` | metadata (PID, command, project_root) |
| Host registry of projects | `~/.forktex/registry.json` | metadata |
| Agent conversation history | `<root>/.forktex/agents/history/<id>.jsonl` | varies — could contain prompts/code |

Out of scope: protecting against a fully-compromised local user account,
kernel-level adversaries, or a compromised remote service we connect to.

---

## What's already in place

### 1. Filesystem permissions

`forktex_cloud.paths.ensure_global_dir()` creates `~/.forktex/` with
mode `0o700` on POSIX (Windows relies on per-user ACLs on `%APPDATA%`).
This means nothing under `~/.forktex/` is readable by other local users
on a multi-user machine.

**Verify on go-live:**
```bash
stat -c '%a %n' ~/.forktex/
# expect: 700 /home/<user>/.forktex
```

### 2. Atomic writes through `tracked_write`

All write entry points into `.forktex/` route through
`forktex.graph.io_proxy.tracked_write`, which:
1. Writes to a sibling tempfile (prefix `.<name>.`, suffix `.tmp`).
2. Atomically renames over the destination via `os.replace`.

Crash mid-write never produces a half-written secret on disk. The only
window where the tempfile exists has the same `0o700` parent directory
permission, so it's not exposed to other users either.

### 3. Structure-spec enforcement

`forktex.graph.structure` carries a canonical list of allowed paths inside
`.forktex/` (project) and `~/.forktex/` (host). `tracked_write` rejects
writes to any path not in the spec — by default raising
`StructureViolation`. This means a compromised dependency or an SDK that
suddenly tries to drop a file into `.forktex/` somewhere it shouldn't is
**stopped at the call site** rather than silently succeeding.

For development convenience, `FORKTEX_STRUCTURE_LENIENT=1` downgrades
violations to warnings. **Production deployments should leave that env
var unset.**

### 4. AOP audit safety net

`forktex.graph.io_proxy.install_audit_hook` registers a `sys.audit` hook
that surfaces any **direct** write (one that didn't go through
`tracked_write`) into a `.forktex/` path as a `WARNING` log message. The
hook is observation-only — it never blocks I/O — but in development logs
it makes any third-party SDK that bypasses `tracked_write` immediately
visible.

Subprocess writes (e.g. `git`, `docker compose`, scraper child
processes) bypass the hook by definition. The host-scope graph build
reconciles by walking `~/.forktex/**` and known project `.forktex/**`
against the registry, back-filling any drift.

### 5. SDK-boundary guard for cross-repo writes

Calls into sibling SDKs (`forktex_cloud.bridge.local_compose.write_local_compose`
in particular) are wrapped with `@sdk_boundary`. The decorator:
1. Snapshots `.forktex/` before the call (mtime + sha256-12 per file).
2. Lets the SDK run.
3. Diffs the post-call state and validates each new/changed file
   against the structure spec.

In strict mode (default) any unspec'd file the SDK produced raises a
`StructureViolation`. This caught a real bug live — the cloud SDK
previously emitted a build context at `.forktex/redis/` that doesn't
exist; the boundary surfaced it as a structure violation rather than a
silent docker-compose failure.

### 6. Secret-bearing entries are tagged

The structure spec marks each entry with a `sensitivity` field
(`public` | `config` | `secret`). The current `secret`-tagged entries:

```
project: intelligence.json, network.json, vault/*/secrets.enc,
         state/keys/*.key, ssl/custom/**, backups/**
host:    cloud.json, intelligence.json, network.json
```

`forktex.graph.structure.secret_entries(scope)` enumerates them
programmatically — useful for backup tooling that needs to know what to
encrypt before leaving the machine.

### 7. Defence-in-depth `.gitignore`

The lifecycle writes a `.gitignore` at three points:
1. The project's root `.gitignore` (managed by `_cloud_paths._ensure_gitignore_block`) excludes `.forktex/**` except `.forktex/.version`.
2. `<root>/.forktex/.gitignore` (`* / !.gitignore / !.version`) — protects against a stripped or missing root block.
3. `~/.forktex/.gitignore` — guards against a stray `git init` in `$HOME`.

This means even if a contributor strips the project root's gitignore, the inner gitignore still prevents secrets from being committed.

---

## Recommended hardening for go-live

### A. Permission audit script

Bake into your post-install verification:

```bash
#!/usr/bin/env bash
# Enforce 0700 on global, 0600 on every secret-tagged file.
chmod 700 ~/.forktex
find ~/.forktex -maxdepth 2 \( -name 'cloud.json' -o -name 'intelligence.json' \
  -o -name 'network.json' \) -exec chmod 600 {} +
find <project>/.forktex/state/keys -name '*.key' -exec chmod 600 {} +
find <project>/.forktex/vault -name 'secrets.enc' -exec chmod 600 {} +
```

For automated environments add this to the CI image's healthcheck.

### B. Strict structure mode

Ensure `FORKTEX_STRUCTURE_LENIENT` is **never** set in production. CI:

```bash
[ -z "${FORKTEX_STRUCTURE_LENIENT}" ] || { echo "lenient mode set; refusing"; exit 1; }
```

`forktex graph audit --scope project` should also be a CI gate — any
"unknown" entries in `.forktex/` should fail the build:

```bash
forktex graph audit --scope project | grep -E '^[ ]*\?' && exit 1 || exit 0
```

### C. Vault-only secrets

For per-project secrets, the only sanctioned location is
`<root>/.forktex/vault/{env}/secrets.enc` (Fernet-encrypted). Plaintext
config files (`config.json`, `cloud/config.json`) **must not** carry
tokens or passwords. Code review checklist: search reviewed PRs for any
new field added to `config.json` whose name contains `token`, `key`,
`secret`, `password` — push it into the vault instead.

### D. Bash-tool gating for autonomous agents

`bash_execute` (in `forktex.agent.tools.bash`) gives the agent a real
shell. For autonomous (non-interactive) loops, gate it:

1. Run the agent under a **dedicated UNIX user** with a restricted
   profile so even worst-case command execution can't escalate.
2. Set `--max-iterations` and a wall-clock timeout on the agent loop.
3. For high-trust automations (e.g. CI bots), deny `bash_execute`
   entirely — pass `extra_tools=` only to `ToolServer` and skip the
   bash factory.

### E. Telemetry posture

ForkTex is local-first — there is **no phone-home** in the CLI. No
analytics, no opt-out flags, no usage pings. The only outbound traffic
the CLI makes is to the three platform endpoints you've configured
(`https://intelligence.forktex.com/api`, your `cloud` controller, your
`network` API). If you operate in a sealed environment, set the
endpoints to internal hosts via `connect --endpoint` and verify with
`forktex status`.

### F. Live-instance leak window

`~/.forktex/instances/<run_id>.json` records `pid`, `command`,
`project_root`, `started_at`, `last_heartbeat_at`. None of those are
secrets, but the `command` field captures the full argv — including
flags like `--api-key=` if a user passes a credential on the command
line. **Recommendation**: discourage `--api-key` on the command line in
favour of `connect`'s interactive prompt or `FORKTEX_*_API_KEY` env
vars. Add a redactor in `forktex.runtime.instance.create_instance` that
masks any argv element matching `^--api[-_]key=`.

### G. Subprocess command logging in agent history

Agent JSONL history (`<root>/.forktex/agents/history/<id>.jsonl`)
records every tool call including `bash_execute` invocations and stdout
snippets. If your agents are allowed to read secrets out of the vault
(via your own decorated tool), that data ends up in the history file.
**Recommendation**: append-only mode, `0o600` on the history file, and a
configurable `redact_patterns` regex list applied in
`forktex.agent.state.AgentStateStore.append`.

### H. Dependency surface

`pip-audit` runs on every CI cycle (`make audit`). On go-live:
1. Pin SDK versions tightly in `pyproject.toml`'s `dependencies`
   (already the case: `forktex-cloud (>=0.2.3,<0.3.0)`).
2. Run `make audit` weekly via cron or GitHub Actions schedule.
3. For air-gapped customers, mirror `forktex` + its three SDK deps to
   an internal PyPI; `pip install --index-url` from there.

### I. Update / rollback story

Customers running `forktex` in production should pin a specific version
in their automation:

```bash
pipx install 'forktex==0.2.6'   # not bare `forktex`
```

Major bumps should be rolled out per-project with a test machine first.
The `<root>/.forktex/.version` file records the on-disk schema version
(currently `1`); a future schema bump triggers a one-shot migration on
first invocation rather than silent breakage.

---

## Reporting

Report security issues privately to **info@forktex.com** with subject
`[SECURITY] forktex-py: <one-line summary>`. We aim to acknowledge
within 2 business days. Please do **not** open a public GitHub issue
for vulnerabilities until a fix is shipped.
