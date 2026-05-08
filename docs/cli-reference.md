# CLI reference

`forktex` is a single binary with three peer services — **intelligence**, **cloud**, **network** — plus built-in commands for project inspection (`graph`), the delivery-standard audit (`fsd`), and lifecycle helpers (`status`, `clean`, `serve`, `agents`). All three services share the same credential verbs (`connect` / `disconnect`).

## Built-in vs. platform

What works offline, what needs which platform connection:

| Command group        | Needs no platform | Needs `intelligence` | Needs `cloud` | Needs `network` |
|----------------------|:-----------------:|:--------------------:|:-------------:|:---------------:|
| `forktex graph …`    | ✅                |                      |               |                 |
| `forktex fsd …`      | ✅                |                      |               |                 |
| `forktex agents …`   | ✅                |                      |               |                 |
| `forktex serve`      | ✅                |                      |               |                 |
| `forktex clean`      | ✅                |                      |               |                 |
| `forktex` (chat REPL)| menu only         | ✅ (chat upgrade)    |               |                 |
| `forktex intelligence ask/run/scrape` | |     ✅                |               |                 |
| `forktex cloud up/deploy/server/…`    | |                      | ✅            |                 |
| `forktex network status`              | |                      |               | ✅              |

`forktex status` works with or without a connection — it shows the project + environment + which services are signed in.

```
forktex                      Bare: menu-driven root loop (auto-upgrades to chat REPL)
forktex --version            Print version
forktex status               Project + environment + auth state across all services
```

## Services

```
forktex intelligence
  connect / disconnect       Authenticate / remove credentials
  status                     API health + whoami
  ask "..."                  Single-shot question (scriptable)
  run "..."                  Orchestrated task (multi-step, tool-using)
  scrape <url>               Agentic browser scraper (Playwright)
  index-ecosystem            Knowledge ingestion across sibling repos

forktex cloud
  connect / disconnect       Authenticate / remove credentials
  init                       Scaffold forktex.json manifest
  up / down                  Start / stop stack from manifest
  deploy <server-id>         Blue-green deployment
  server | project | vault   Per-resource subgroups
  status / logs / events     Monitoring

forktex network
  connect / disconnect       Authenticate / remove credentials
  status                     identity_me round-trip
```

## Cross-cutting groups

```
forktex graph
  build                      Refresh .forktex/graph.{json,dsl,html}
  show                       Render as tree | json | dsl on stdout
  c4                         Per-platform C4 view (DSL or drill-down HTML)
  audit                      Validate the .forktex/ footprint against the spec
  ecosystem                  Walk every forktex.json under a parent dir
  diff                       Compare two graph snapshots
  importers <target>         Modules that import a library / package / module
  package <rel-path>         Locate the package containing a path
  modules <pattern>          Glob over module names
  recent                     Files inside .forktex/ touched in the last N hours

forktex fsd
  check [--recursive]        Verify FSD compliance; recurse into nested forktex.json
  report                     Generate FSD evidence pack (JSON + HTML)
  ecosystem                  FSD level matrix across every project under a parent dir
  makefile sync              Regenerate Makefile from forktex.json atoms

forktex agents
  list                       Recent agent runs from history
  show <id>                  Detail of one run
  cancel <id>                Cancel a running agent
  ground                     Regenerate AGENTS.md across sibling repos
  root                       Start the persistent ecosystem-aware agent

forktex serve                Live web dashboard (graph + C4 + structure spec)
forktex clean                Remove generated artifacts; forget missing projects
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
