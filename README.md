<p align="center">
  <img src="./docs/banner.svg" alt="forktex" height="96">
</p>

<p align="center">
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/v/forktex.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/forktex/"><img src="https://img.shields.io/pypi/pyversions/forktex.svg" alt="Python"></a>
  <a href="https://github.com/forktex/forktex-py/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/forktex.svg" alt="License"></a>
</p>

<p align="center"><em>A local AI-engineering CLI. Optionally talks to three ForkTex platforms.</em></p>

`forktex` ships as a single binary. By itself it gives you an agent that reads your repo, runs commands, writes patches, audits your delivery standard, and discovers your architecture — no account required. Plug in any of the three ForkTex platforms (cloud, intelligence, network) and the same CLI gains LLM reasoning, infra deploys, and identity / projects / channels.

---

## Install

**One-liner** (Linux / macOS):

```bash
curl -sSL install.forktex.com/sh | sh
```

**One-liner** (Windows, PowerShell 5.1+):

```powershell
iwr -useb install.forktex.com/ps | iex
```

The installer detects Python ≥ 3.12, prefers `pipx` (isolated install), falls back to `pip --user`, and seeds the config directory automatically.

**Manual:**

```bash
pipx install forktex      # recommended — isolates deps
pip install --user forktex
```

Requires **Python 3.12+**. Tested on 3.12 / 3.13 / 3.14.

---

## Built-in — works with zero credentials

Everything in this section runs without connecting to any platform. The CLI ships its own agents, tools, architecture mapper, and delivery-standard checker.

### 🎛  Chat REPL with agents

Bare `forktex` opens the menu. The two heavyweight agents live under `forktex agents`:

```bash
forktex                  # menu (auto-upgrades to chat when intelligence is connected)
forktex agents root      # persistent ecosystem-aware agent — reads AGENTS.md,
                         # the C4 snapshot, and your full project context as system prompt
forktex agents ground    # regenerate AGENTS.md across sibling repos
forktex agents list      # history of agent runs
forktex agents show <id> # inspect one run
```

### 🛠  A real tool surface, not a wrapper

The agent calls into a single tool registry — the same shape an MCP server would expose, just in-process:

| Tool        | What it covers |
|-------------|----------------|
| filesystem  | `read_file`, `write_file`, `patch_file`, `delete_file`, `list_directory`, `glob_search`, `grep_search` |
| bash        | command execution with streaming output and timeouts |
| git         | `status`, `log`, `diff`, `blame`, `commit`, `push` |
| web         | DuckDuckGo `web_search` + Playwright-rendered `web_fetch` |
| scraper     | 12-tool stateful browser session (navigate, click, type, fill, screenshot, …) |

> **About MCP:** the CLI itself is *MCP-style* (one registry, structured calls) but does not run an MCP server. The MCP endpoint lives on the platform side — see [`cloud`](#three-platforms--one-cli) and its `/api/mcp`.

### 🗺  Architecture discovery

```bash
forktex arch discover
```

Parses `forktex.json` (containers/services), `pyproject.toml` + `package.json` (tech stack), the filesystem (components), and Git metadata, and emits a C4 model as a JSON snapshot, a Structurizr DSL file, and an interactive HTML visualization with topology graph, port inventory, and dependency edges.

### ✅  ForkTex Standard for Delivery

```bash
forktex fsd check          # profile-driven Make-target audit (per-atom, per-facet, per-level)
forktex fsd report         # ISO-grade JSON + HTML evidence
forktex fsd makefile sync  # regenerate Makefile from forktex.json atoms (don't hand-edit)
```

`fsd check` evaluates each project against profiles like `workspace/python-monorepo` or `package/python-library`, runs the atom commands defined in `forktex.json`, and reports satisfied / failed / skipped per atom plus per-level achievement.

---

## Three platforms · One CLI

Three platforms sit on the same shelf — each speaks the same `connect` / `disconnect` verbs, each lives at `forktex <platform> …`, each has a Python SDK, and each exposes an MCP endpoint at `/api/mcp` so AI assistants can read and write directly with the user's permissions.

<table>
<tr>
<td align="center" width="33%">
  <img src="https://cloud.forktex.com/assets/forktex-cloud-icon-BR2uDJyk.svg" height="64" alt="ForkTex Cloud"><br>
  <strong>cloud</strong><br>
  <sub>infra & deploys</sub>
</td>
<td align="center" width="33%">
  <img src="https://cloud.forktex.com/assets/forktex-intelligence-icon-COh1kdep.svg" height="64" alt="ForkTex Intelligence"><br>
  <strong>intelligence</strong><br>
  <sub>LLM, embeddings, search</sub>
</td>
<td align="center" width="33%">
  <img src="https://cloud.forktex.com/assets/forktex-network-icon-DKrK_c7g.svg" height="64" alt="ForkTex Network"><br>
  <strong>network</strong><br>
  <sub>identity, projects, channels</sub>
</td>
</tr>
<tr>
<td>

```bash
forktex cloud connect
forktex cloud up --env local
forktex cloud deploy <id>
```

Bring up local stacks; blue-green deploy from `forktex.json`.

</td>
<td>

```bash
forktex intelligence connect
forktex intelligence ask  "..."
forktex intelligence run  "..."
```

LLM, embeddings, agentic runs.

</td>
<td>

```bash
forktex network connect
forktex network status
```

Identity, projects, tasks, worklogs.

</td>
</tr>
</table>

> 🧠 **Intelligence is what makes `forktex` chat smart.** The built-in agents above run with or without it; connect intelligence and bare `forktex` upgrades into a streaming chat REPL backed by an LLM. Cloud and network sit on the same level — connect any, all, or none.

### Three ways to reach a platform

```
       ╭──────────────╮     ╭──────────────╮     ╭──────────────╮
       │  ☁  cloud    │     │  🧠 intelligence │     │  🕸  network  │
       ╰──────┬───────╯     ╰──────┬───────╯     ╰──────┬───────╯
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
        ╭─────┴─────╮        ╭─────┴─────╮        ╭─────┴─────╮
        │  forktex  │        │ /api/mcp  │        │   pip /   │
        │    CLI    │        │   (MCP)   │        │    SDK    │
        ╰─────┬─────╯        ╰─────┬─────╯        ╰─────┬─────╯
              │                    │                    │
            you             AI assistants        your codebase
```

| | Path | One-liner |
|---|------|-----------|
| 💻 | **`forktex` CLI** | `forktex` drops you in. Fastest path for humans — chat, deploy, audit, all in one binary. |
| 🤖 | **MCP** (`/api/mcp`) | AI assistants read and write through Model Context Protocol with the credentials of the user who connected them. |
| 🔌 | **Python SDK** | `pip install forktex-cloud  ·  forktex-intelligence  ·  forktex-network` — same auth, same shapes. |

> Same data model on every path. A row created by an MCP-connected agent, a script using the SDK, and you typing `forktex network …` are indistinguishable to the platform.

---

## 60-second tour

```bash
# Built-in (no platform needed)
forktex agents root                            # ecosystem-aware local agent
forktex arch discover                          # C4 model as JSON / DSL / HTML
forktex fsd check                              # delivery-standard audit

# Connect a platform (idempotent — login or register)
forktex intelligence connect
forktex cloud connect --api-key ftx-…
forktex network connect --endpoint http://localhost:9000 --email you@example.com

# Now the smart things light up
forktex                                        # bare → chat REPL (intelligence)
forktex intelligence ask "What does this project do?"
forktex cloud up --env local --build           # bring infra up from forktex.json
forktex status --json | jq '.intelligence.connected'
```

---

## Documentation

| Topic | Where |
|-------|-------|
| Full CLI reference (every verb, every slash command, every keybind) | [docs/cli-reference.md](docs/cli-reference.md) |
| Credentials — verbs, options, on-disk layout | [docs/credentials.md](docs/credentials.md) |
| Configuration — env vars, manifest, ecosystem layout | [docs/configuration.md](docs/configuration.md) |
| Development — `make ci`, license headers, sibling SDK editable installs | [docs/development.md](docs/development.md) |

---

## License

Dual-licensed — **AGPL-3.0-or-later** for open-source use, **commercial** for everything else (proprietary products, SaaS without source release, redistribution in closed-source form). See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for the full terms.

Commercial licensing inquiries: **info@forktex.com**.
