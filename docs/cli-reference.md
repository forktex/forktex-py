# CLI reference

`forktex` is a single binary with three peer services — **intelligence**, **cloud**, **network** — plus cross-cutting groups for delivery-standard checks (`fsd`), architecture discovery (`arch`), and multi-repo git (`git`). All three services share the same credential verbs (`connect` / `disconnect`).

## Built-in vs. platform

What works offline, what needs which platform connection:

| Command group        | Needs no platform | Needs `intelligence` | Needs `cloud` | Needs `network` |
|----------------------|:-----------------:|:--------------------:|:-------------:|:---------------:|
| `forktex agents …`   | ✅                |                      |               |                 |
| `forktex arch …`     | ✅                |                      |               |                 |
| `forktex fsd …`      | ✅                |                      |               |                 |
| `forktex git …`      | ✅                |                      |               |                 |
| `forktex local …`    | ✅                |                      |               |                 |
| `forktex` (chat REPL)| menu only         | ✅ (chat upgrade)    |               |                 |
| `forktex intelligence ask/run/scrape` | |     ✅                |               |                 |
| `forktex cloud up/deploy/server/…`    | |                      | ✅            |                 |
| `forktex network status`              | |                      |               | ✅              |

`forktex status` and `forktex info` work without any platform — they just report which connections exist.

```
forktex                      Bare: menu-driven root loop (auto-upgrades to chat REPL)
forktex --version            Print version
forktex status               Aggregate credential state (cloud + intelligence + network)
forktex info                 Project + environment summary
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
forktex fsd
  check                      Verify FSD compliance against the active profile
  report                     Generate ISO audit evidence
  makefile sync              Regenerate Makefile from forktex.json atoms

forktex arch
  discover                   C4 auto-discovery from the codebase

forktex git
  status-all                 Multi-repo git status

forktex overview             Ecosystem overview (siblings, versions, drift)
forktex present              Pretty-print project context
forktex agents               Local tool-server agents (ground, root)
forktex local                Local-only utilities
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
