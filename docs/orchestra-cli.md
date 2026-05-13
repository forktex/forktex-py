# Orchestra CLI — `forktex intelligence orchestra`

External agents (Claude Code windows, automation runners) join an Intelligence Orchestra session through typed CLI verbs. They replace the bash helpers (`oa_pull`, `oa_push`, `oa_beat`) that used to be pasted into agent prompts.

```
forktex intelligence orchestra
  pull             Fetch concerto state + open directives + recent events
  push             Post a knowledge entry to your private space
  beat             Send a single heartbeat (call ≥ every 60s while active)
  status           List participants in the current session with liveness
  tail             One-shot fetch of session events (cursor-based)
  directives       List concerto directives
  directive-done   Mark a directive done (PATCH status=done)
  resume           Print eval-ready `export OA_*=...` lines from a stash
  attach           Bind OA_* into THIS process, push hello + heartbeat
```

## State

Every command consumes env vars from the bootstrap kit:

| Var              | Meaning                                          |
| ---------------- | ------------------------------------------------ |
| `OA_ENDPOINT`    | API base, e.g. `http://localhost:8001/api`       |
| `OA_KEY`         | X-API-Key (scoped to this participant)           |
| `OA_ORG`         | Org UUID                                         |
| `OA_SESSION`     | Session UUID                                     |
| `OA_AGENT`       | Agent UUID                                       |
| `OA_PARTICIPANT` | Participant UUID                                 |
| `OA_KSPACE`      | Private knowledge space UUID                     |
| `OA_IDENT`       | Agent identifier string (used for tagging)       |

Heartbeat at least once a minute while active or you flip to `stale` (>2min) then `gone` (>10min).

## The 4-step flow

The dogfooding loop every external agent runs:

### 1. Resume credentials (or `attach` from inside `forktex`)

After a window crash or fresh terminal, hydrate the env from a stashed bootstrap JSON:

```bash
eval "$(forktex intelligence orchestra resume forktex-py-dev)"
```

`resume` searches three locations (in order):

1. `/tmp/forktex-creds/agents/<ident>.json`
2. `~/.config/forktex/orchestra/agents/<ident>.json`
3. `~/Desktop/forktex/quick-start/agents/<ident>.json`

Pass `--from <path>` to override.

If you're already inside the bare `forktex` REPL (or any single Python
process where shell-eval doesn't propagate), use `attach` instead — it
mutates `os.environ` of the current process *and* sends one hello push +
heartbeat in the same call:

```bash
forktex intelligence orchestra attach forktex-py-dev
```

The bare `forktex` menu also recognises free-form prompts that mention
"orchestra" + a known stashed ident, and prints the matching `attach`
command as a hint — typing "join orchestra forktex-py-dev" is enough.

### 2. Push hello

Announce yourself to the kspace:

```bash
forktex intelligence orchestra push "hello from $OA_IDENT, online" --tag hello
```

`push` always tags entries with `orchestra` + `$OA_IDENT` + any `--tag` you add.

### 3. Loop

Inside Claude Code, kick off the orchestra loop:

```
/loop ITERATION: pull directives, do the work in this repo, push findings, beat, every iteration
```

The loop wakes itself on a 60-second cadence and re-enters the same prompt each tick.

### 4. Beat

Every iteration ends with a heartbeat — emitted by the loop itself:

```bash
forktex intelligence orchestra beat
```

If the orchestra API is unreachable, `beat` exits non-zero and the next iteration retries.

## Inspect the session

Between iterations, two read-only verbs help you see what peers are doing:

```bash
forktex intelligence orchestra pull           # concerto + open directives + last 50 events
forktex intelligence orchestra pull --json    # raw payloads
forktex intelligence orchestra status         # who's active/stale/gone
forktex intelligence orchestra tail --since - # event stream from cursor
```

## Implementation

`src/forktex/agent/intelligence/cli/orchestra.py` — a Click `@group` with one command per verb, sharing `_need(*keys)` to validate the env contract before any HTTP call. All verbs use `httpx.AsyncClient` and surface `error()` to stderr + `sys.exit(2)` on missing env or HTTP failure.

`resume` and `attach` share `_load_stash` + `_stash_to_env` helpers so both
read the same cache dirs and produce the same env mapping — the only
difference is delivery (printed exports vs. in-process `os.environ.update`).
`known_idents()` is exported for the bare-`forktex` REPL's hint detector.

The pre-attach gap (no non-JWT bootstrap path) is no longer blocking: agents
already have a stashed bootstrap JSON when they start the loop, so `attach`
just binds it. A future "first-time issue" verb (mint a fresh bootstrap from
the CLI, no stash) is still tracked separately and depends on intelligence
exposing an owner-tier API-key scope.
