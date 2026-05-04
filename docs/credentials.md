# Credentials

Every service understands the same verb pair (`connect` / `disconnect`) and the same option set. Credentials live in JSON files under `~/.forktex/` (global) or `<project>/.forktex/` (per-project) — see the [forktex directory spec](https://github.com/forktex/cloud/blob/master/docs/forktex-directory-spec.md) for the complete on-disk layout.

## One verb, three services

```bash
forktex status                                              # aggregate table (all 3 services)

forktex cloud connect                                       # email/password + org select
forktex cloud connect --api-key ftx-…                       # non-interactive

forktex intelligence connect                                # idempotent: login or register
forktex intelligence connect --new                          # force register

forktex network connect --endpoint http://localhost:9000 \
                        --email you@example.com

forktex <service> disconnect [--global]                     # remove saved creds
```

## Common options

| Option | Meaning |
|--------|---------|
| `--endpoint` / `--url` | Override the service base URL |
| `--email` | Account email |
| `--password` | Account password (omit to prompt) |
| `--api-key` | Skip interactive login |
| `--global` | Write to `~/.forktex/` instead of `<project>/.forktex/` |
| `--new` | Force registration (intelligence / network) |

## Where credentials live

```
~/.forktex/cloud.json              global
~/.forktex/intelligence.json       global
~/.forktex/network.json            global

<project>/.forktex/cloud.json      project-scoped (overrides global)
<project>/.forktex/intelligence.json
<project>/.forktex/network.json
```

Project-level files take precedence over global ones. The full directory layout — every file, what writes it, whether it's gitignored — is enforced in code via `forktex_cloud.paths` and specified in the [forktex directory spec](https://github.com/forktex/cloud/blob/master/docs/forktex-directory-spec.md).

## Inline `/connect` inside chat

`/connect <service> [--new]` runs the same implementation as the CLI verb, so you don't need to leave the REPL to authenticate. Service cards flash for 3 seconds on success.
