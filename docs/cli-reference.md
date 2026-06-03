# CLI reference

`forktex` is an **agent over one knowledge substrate**, exposed as eight
top-level commands in four categories (the authoritative taxonomy lives in
`forktex.agent.cli_help.CATEGORIES`):

- **Core** — `chat`, `run` (talk to the agent / one orchestrated run)
- **Grounding** — `knowledge`, `arch` (the substrate · the structural authority)
- **Services** — `cloud`, `fsd`, `auth` (deploy & operate · delivery audit · credentials)
- **Housekeeping** — `clean`

FSD lifecycle verbs (`test`, `build`, `apply`, …) are **not** CLI commands —
`make` owns lifecycle (the Makefile is generated from `forktex.json`).

## Built-in vs. platform

What works offline, what needs which platform connection:

| Command group        | Needs no platform | Needs `intelligence` | Needs `cloud` | Needs `network` |
|----------------------|:-----------------:|:--------------------:|:-------------:|:---------------:|
| `forktex arch …`     | ✅                |                      |               |                 |
| `forktex knowledge …`| ✅                |  (ingest --remote)   |               |                 |
| `forktex fsd …`      | ✅                |                      |               |                 |
| `forktex auth …`     | ✅                |                      |               |                 |
| `forktex clean`      | ✅                |                      |               |                 |
| `forktex` / `chat`   | menu only         | ✅ (chat upgrade)    |               |                 |
| `forktex run "…"`    |                   | ✅                   |               |                 |
| `forktex cloud up/deploy/server/…` |    |                      | ✅            |                 |

```
forktex                      Bare: menu-driven root loop (auto-upgrades to chat REPL)
forktex --version            Print version
forktex auth                 Project + environment + auth state across all services
```

## Core — the agent

```
forktex chat                 Interactive chat REPL, grounded on the current project
  --ecosystem                Ground on the whole workspace (parent docs/AGENTS.md + cross-project knowledge)
  --desktop                  Enable observe-only desktop tools
forktex run "<task>"         One orchestrated, tool-using agentic run (scriptable)
```

## Grounding — the substrate + the structural authority

```
forktex knowledge            The knowledge base (docs ← global ← project)
  search "<query>"           Tokenised, ranked search over the composed graph
  show <id>                  Print a node in full (frontmatter + body)
  list                       List node summaries
  neighbors <id>             A node's typed adjacency (in/out edges by kind)
  recycle <id> [--global]    Capture a learning back (--global → ~/.forktex/knowledge)
  retire <id>                Mark a node retired (filtered from grounding)
  rollup <parent-id>         Compact a subtree into its parent summary
  doctor [--composed]        Drift report — broken refs, cycles, retired-but-referenced
  ingest [--remote]          Bulk-import a source (ecosystem AGENTS.md → remote vector store)
  init                       Bootstrap <project>/.forktex/knowledge/
  mcp                        Run an MCP server (stdio) exposing the knowledge tools

forktex arch                 Structural authority — one graph build, two faces
  build [--no-bundle]        graph.{json,dsl,html} + agent-grounding manual_bundle.json
  show                       Render as tree | json | dsl on stdout
  c4                         Per-platform C4 view (DSL or drill-down HTML)
  search "<kw>"              Ranked keyword search over graph nodes/edges
  serve                      Live web dashboard at http://localhost:4444
  diff                       Compare two graph snapshots
  importers <target>         Modules that import a library / package / module
  package <rel-path>         Locate the package containing a path
  modules <pattern>          Glob over module names
  recent                     Files inside .forktex/ touched in the last N hours
  ecosystem                  Walk every forktex.json under a parent dir
  audit                      Validate the .forktex/ footprint against the spec
```

## Services

```
forktex cloud                Deploy & operate (connect / disconnect like every service)
  init / new                 Scaffold a forktex.json manifest / project from a template
  up [--env local] / down    Start (remote deploy or local stack) / tear down
  deploy <server-id>         Push a new release (blue-green)
  server | project | vault   Per-resource subgroups
  status / logs / events     Monitoring + audit
  inspect / tree / dns / ssl Resource inspection + edge config

forktex fsd                  Delivery standard (pass `-d <dir>` at the group level)
  check [--recursive]        Verify FSD compliance; recurse into nested forktex.json
  report                     Generate the FSD evidence pack (JSON + HTML)
  ecosystem                  FSD level matrix across every project under a parent dir
  makefile sync              Regenerate the Makefile from forktex.json atoms

forktex auth                 Aggregate credential state (bare = status table)
  status [--json]            Signed-in state + project + Python + platform
  cloud | intelligence | network
                             Per-service connect / disconnect
```

## Housekeeping

```
forktex clean                Remove generated .forktex/ artifacts; forget missing projects
  --legacy-evidence          Also sweep historical timestamped FSD/arch outputs
```

## Slash commands (chat REPL)

Type `/` for a live dropdown; **Tab** accepts the highlighted entry.

```
/help          show this list
/status        aggregate credential state
/connect       <service> [--new]   idempotent login-or-register
/disconnect    <service>           remove saved credentials
/cards         toggle service cards (hidden by default)
/clear         clear visible buffer
/history       show full transcript
/tools         list local tool-server tools
/menu          exit chat back to menu
/quit          exit forktex
```

## Keybindings (chat REPL)

```
Ctrl+K   toggle service cards          Ctrl+L   clear visible buffer
Ctrl+H   show full transcript          Ctrl+D   exit to menu
Tab      autocomplete slash / service  Enter    submit
```

## Menu keys (pre-chat root loop)

```
c / i / n   drill into service help (cloud / intelligence / network)
s           status
r           refresh probes
h           hide cards
q           quit
Enter       → chat REPL (when intelligence reachable)
/           open the same live dropdown as the chat REPL
```
