# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""``forktex intelligence orchestra`` — external-participant CLI primitives.

Brings the bash-helpers we currently paste into Claude Code windows
(`oa_pull`, `oa_push`, `oa_beat`) up into the forktex CLI so an external
agent can join an Orchestra session via stable, typed commands.

State source for every command: env vars set by the bootstrap kit ::

    OA_ENDPOINT     full API base, e.g. http://localhost:8001/api
    OA_KEY          X-API-Key (scoped to this participant)
    OA_ORG          UUID
    OA_SESSION      UUID
    OA_AGENT        UUID
    OA_PARTICIPANT  UUID
    OA_KSPACE       UUID (private knowledge space for this agent)
    OA_IDENT        identifier string (for tagging)

Use ``forktex intelligence orchestra resume <ident>`` to print eval-ready
``export OA_*=...`` lines from a stashed bootstrap JSON — handy after a
window crash so you can ``eval "$(forktex … resume <ident>)"`` and pick
up exactly where you were without re-pasting credentials.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import asyncclick as click
import httpx

from forktex.agent.ui.console import console, info, error


# ── env / config ─────────────────────────────────────────────────────


_REQUIRED = ("OA_ENDPOINT", "OA_KEY", "OA_ORG", "OA_SESSION")
_PARTICIPANT_OPS = _REQUIRED + ("OA_PARTICIPANT",)
_PUSH_OPS = _REQUIRED + ("OA_KSPACE", "OA_IDENT")


def _need(*keys: str) -> dict[str, str]:
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        error(
            f"missing env: {', '.join(missing)}. "
            "Set the orchestra bootstrap kit (see /tmp/forktex-creds/agents/<ident>.prompt) "
            "or run `forktex intelligence orchestra attach <ident>` to bind a stashed bootstrap."
        )
        sys.exit(2)
    return {k: os.environ[k] for k in keys}


def _base_url(env: dict[str, str]) -> str:
    return f"{env['OA_ENDPOINT']}/org/{env['OA_ORG']}/orchestra/sessions/{env['OA_SESSION']}"


def _headers(env: dict[str, str]) -> dict[str, str]:
    return {"X-API-Key": env["OA_KEY"], "Content-Type": "application/json"}


# ── group ─────────────────────────────────────────────────────────────


@click.group()
async def orchestra():
    """Participate in an Intelligence Orchestra session.

    All commands consume env vars from the bootstrap kit (OA_ENDPOINT,
    OA_KEY, OA_SESSION, …). Heartbeat at least once a minute while
    active or you'll flip to `stale` (>2min) then `gone` (>10min).
    """
    pass


# ── pull ──────────────────────────────────────────────────────────────


@orchestra.command(name="pull")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of a human summary")
async def pull_cmd(as_json: bool) -> None:
    """Fetch concerto state + open directives + recent events."""
    env = _need(*_REQUIRED)
    base = _base_url(env)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        c = await client.get(f"{base}/concerto")
        d = await client.get(f"{base}/concerto/directives")
        e = await client.get(f"{base}/events?limit=50")

    if as_json:
        import json as _json
        out = {
            "concerto": c.json() if c.is_success else {"error": c.status_code},
            "directives": d.json() if d.is_success else [],
            "events": e.json() if e.is_success else [],
        }
        click.echo(_json.dumps(out, indent=2, default=str))
        return

    if c.is_success:
        body = c.json()
        console.print(
            f"[bold]concerto[/bold]  title={body.get('title')!r}  "
            f"phase={body.get('phase')!r}  status={body.get('status')!r}"
        )
    else:
        info(f"concerto fetch returned {c.status_code}")

    if d.is_success:
        directives = d.json()
        opens = [x for x in directives if x.get("status") == "open"]
        console.print(f"[bold]directives[/bold]  total={len(directives)} open={len(opens)}")
        for x in opens[:10]:
            who = x.get("assignee_role") or "—"
            console.print(
                f"  · [{x.get('kind')}] [{x['id'][:8]}] {x.get('title','')[:80]}"
                f"  → role={who}"
            )

    if e.is_success:
        events = e.json()
        console.print(f"[bold]events[/bold]  recent={len(events)}")
        for ev in events[-5:]:
            console.print(f"  · {ev.get('kind'):24s}  actor={ev.get('actor','')[:8]}…")


# ── push ──────────────────────────────────────────────────────────────


@orchestra.command(name="push")
@click.argument("text")
@click.option("--tag", "tags", multiple=True, default=("progress",), help="Extra tag(s); 'orchestra' + ident always added")
@click.option("--kind", default="note", help="Knowledge entry kind (note/finding/analysis/recommendation)")
async def push_cmd(text: str, tags: tuple[str, ...], kind: str) -> None:
    """Post a knowledge entry to your private space."""
    env = _need(*_PUSH_OPS)
    body = {
        "kind": kind,
        "content_text": text,
        "space_id": env["OA_KSPACE"],
        "session_id": env["OA_SESSION"],
        "tags": ["orchestra", env["OA_IDENT"], *tags],
    }
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{env['OA_ENDPOINT']}/org/{env['OA_ORG']}/knowledge", json=body)
    if r.is_success:
        eid = r.json().get("id", "?")
        console.print(f"[bold green]pushed[/bold green]  entry={eid}")
    else:
        error(f"push failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)


# ── beat ──────────────────────────────────────────────────────────────


@orchestra.command(name="beat")
async def beat_cmd() -> None:
    """Send a single heartbeat — call at least every 60s while active."""
    env = _need(*_PARTICIPANT_OPS)
    async with httpx.AsyncClient(timeout=5.0, headers=_headers(env)) as client:
        r = await client.post(f"{_base_url(env)}/participants/{env['OA_PARTICIPANT']}/heartbeat", json={})
    if r.status_code in (200, 204):
        console.print("[green]♥[/green]")
    else:
        error(f"heartbeat failed: HTTP {r.status_code}")
        sys.exit(1)


# ── status ────────────────────────────────────────────────────────────


@orchestra.command(name="status")
async def status_cmd() -> None:
    """List participants in the current session with liveness."""
    env = _need(*_REQUIRED)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.get(f"{_base_url(env)}/participants")
    if not r.is_success:
        error(f"participants fetch failed: HTTP {r.status_code}")
        sys.exit(1)
    parts = r.json()
    console.print(f"[bold]participants[/bold]  total={len(parts)}")
    for p in parts:
        glyph = {"active": "[green]✓[/green]", "stale": "[yellow]~[/yellow]"}.get(
            p.get("status"), "[red]✗[/red]"
        )
        console.print(
            f"  {glyph} {p.get('instance','?'):24s}  "
            f"role={p.get('role') or '—':10s}  "
            f"kind={p.get('agent_kind','?')}"
        )


# ── tail ──────────────────────────────────────────────────────────────


@orchestra.command(name="tail")
@click.option("--since", default="-", help="Cursor offset; '-' = from beginning")
@click.option("--limit", default=50, type=int)
async def tail_cmd(since: str, limit: int) -> None:
    """One-shot fetch of session events (cursor-based)."""
    env = _need(*_REQUIRED)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.get(f"{_base_url(env)}/events?since={since}&limit={limit}")
    if not r.is_success:
        error(f"events fetch failed: HTTP {r.status_code}")
        sys.exit(1)
    rows = r.json()
    for ev in rows:
        actor = (ev.get("actor") or "")[:8]
        console.print(
            f"[dim]{ev.get('offset','')}[/dim]  {ev.get('kind'):24s}  "
            f"actor={actor:9s}  payload={str(ev.get('payload',{}))[:80]}"
        )
    if rows:
        console.print(f"[dim]next-since: {rows[-1].get('offset','')}[/dim]")


# ── directives ────────────────────────────────────────────────────────


@orchestra.command(name="directives")
@click.option("--status", default=None, help="Filter: open|done|null for all")
async def directives_cmd(status: str | None) -> None:
    """List concerto directives — replaces ``curl /concerto/directives``."""
    env = _need(*_REQUIRED)
    url = f"{_base_url(env)}/concerto/directives"
    if status:
        url += f"?status={status}"
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.get(url)
    if not r.is_success:
        error(f"directives fetch failed: HTTP {r.status_code}")
        sys.exit(1)
    rows = r.json()
    console.print(f"[bold]directives[/bold]  total={len(rows)}")
    for d in rows:
        glyph = "[green]✓[/green]" if d.get("status") == "done" else "[yellow]·[/yellow]"
        console.print(
            f"  {glyph} [{d['id'][:8]}] [{d.get('kind','?')}] "
            f"{d.get('title','')[:75]}  → role={d.get('assignee_role') or '—'}  status={d.get('status')}"
        )


@orchestra.command(name="directive-done")
@click.argument("directive_id")
async def directive_done_cmd(directive_id: str) -> None:
    """Mark a directive as done — replaces curl PATCH ``status=done``."""
    env = _need(*_REQUIRED)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.patch(
            f"{_base_url(env)}/concerto/directives/{directive_id}",
            json={"status": "done"},
        )
    if not r.is_success:
        error(f"PATCH failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    body = r.json()
    console.print(
        f"[bold green]done[/bold green]  [{body['id'][:8]}] {body.get('title','')[:60]}"
    )


# ── resume ────────────────────────────────────────────────────────────


_CACHE_DIRS = (
    "/tmp/forktex-creds/agents",
    str(__import__("pathlib").Path.home() / ".config" / "forktex" / "orchestra" / "agents"),
    str(__import__("pathlib").Path.home() / "Desktop" / "forktex" / "quick-start" / "agents"),
)


def _find_bootstrap(ident: str) -> str | None:
    import pathlib
    for d in _CACHE_DIRS:
        p = pathlib.Path(d) / f"{ident}.json"
        if p.exists():
            return str(p)
    return None


def _load_stash(ident: str, from_path: str | None) -> tuple[str, dict]:
    """Locate + parse the bootstrap JSON for *ident*. Exits 2 on failure."""
    import json as _json

    path = from_path or _find_bootstrap(ident)
    if not path:
        error(
            f"no bootstrap stash found for {ident!r}. "
            f"Searched: {', '.join(_CACHE_DIRS)}. "
            f"Pass --from <path> to a bootstrap JSON."
        )
        sys.exit(2)
    with open(path) as f:
        return path, _json.load(f)


def _stash_to_env(ident: str, d: dict, org_id: str | None) -> dict[str, str]:
    """Assemble the OA_* env mapping from a parsed stash. Exits 2 if no org."""
    import os as _os

    org = org_id or _os.environ.get("OA_ORG") or _extract_org(d)
    if not org:
        error("could not derive OA_ORG from the stash; pass --org-id explicitly")
        sys.exit(2)
    return {
        "OA_ENDPOINT": d["endpoint"],
        "OA_KEY": d["api_key"],
        "OA_ORG": org,
        "OA_SESSION": d["session_id"],
        "OA_AGENT": d["agent_id"],
        "OA_PARTICIPANT": d["participant_id"],
        "OA_KSPACE": d.get("knowledge_space_id") or "",
        "OA_IDENT": ident,
    }


@orchestra.command(name="resume")
@click.argument("ident")
@click.option("--org-id", default=None, help="Org UUID (defaults to env or first matching bootstrap)")
@click.option("--from", "from_path", default=None, help="Explicit path to a bootstrap JSON (overrides cache search)")
async def resume_cmd(ident: str, org_id: str | None, from_path: str | None) -> None:
    """Print eval-ready ``export OA_*=...`` lines for a stashed agent.

    Usage::

        eval "$(forktex intelligence orchestra resume forktex-py-dev)"

    The bootstrap JSON is found in (in order):
      1. /tmp/forktex-creds/agents/<ident>.json
      2. ~/.config/forktex/orchestra/agents/<ident>.json
      3. ~/Desktop/forktex/quick-start/agents/<ident>.json

    If none are present, an explicit ``--from <path>`` is required.
    """
    _, d = _load_stash(ident, from_path)
    env = _stash_to_env(ident, d, org_id)
    click.echo("\n".join(f"export {k}='{v}'" for k, v in env.items()))


# ── sync primitives: claims / barriers / locks ────────────────────────
#
# Server endpoints live at:
#   POST   /sessions/{sid}/sync/claims                        create claim
#   GET    /sessions/{sid}/sync/claims                        list claims
#   PATCH  /sessions/{sid}/sync/claims/{cid}                  update claim
#   DELETE /sessions/{sid}/sync/claims/{cid}                  release claim
#   POST   /sessions/{sid}/sync/barriers                      create barrier
#   GET    /sessions/{sid}/sync/barriers/{bid}                inspect barrier
#   POST   /sessions/{sid}/sync/barriers/{bid}/signal         signal barrier
#   POST   /sessions/{sid}/sync/locks/acquire                 acquire lock
#   POST   /sessions/{sid}/sync/locks/release                 release lock
#   POST   /sessions/{sid}/sync/locks/renew                   renew lock
#
# All mirror the wire shape from intelligence/api/src/orchestra/schemas.py.


@orchestra.command(name="claim")
@click.argument("unit")
@click.argument("intent")
@click.option("--ttl-s", type=int, default=3600, help="Claim TTL in seconds (60-86400)")
@click.option("--shared", is_flag=True, help="Non-exclusive claim (default: exclusive)")
async def claim_cmd(unit: str, intent: str, ttl_s: int, shared: bool) -> None:
    """Create a work-unit claim. Conflict (409) means another agent holds it exclusively."""
    env = _need(*_REQUIRED, "OA_AGENT", "OA_IDENT")
    body = {
        "agent_id": env["OA_AGENT"],
        "unit": unit,
        "intent": intent,
        "exclusive": not shared,
        "ttl_s": ttl_s,
        "progress": {},
    }
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{_base_url(env)}/sync/claims", json=body)
    if r.status_code == 409:
        error(f"conflict: {r.text[:200]}")
        sys.exit(3)
    if not r.is_success:
        error(f"claim create failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    c = r.json()
    console.print(
        f"[bold green]claimed[/bold green] [{c['id'][:8]}] unit={c['unit']} "
        f"intent={c['intent'][:60]} exclusive={c['exclusive']}"
    )


@orchestra.command(name="claims")
@click.option("--unit", default=None, help="Filter by work-unit name")
@click.option("--mine", is_flag=True, help="Only show claims held by this OA_AGENT")
async def claims_cmd(unit: str | None, mine: bool) -> None:
    """List claims in this session."""
    env = _need(*_REQUIRED)
    qs = []
    if unit:
        qs.append(f"unit={unit}")
    if mine:
        env_with_agent = _need(*_REQUIRED, "OA_AGENT")
        qs.append(f"agent_id={env_with_agent['OA_AGENT']}")
    url = f"{_base_url(env)}/sync/claims" + (f"?{'&'.join(qs)}" if qs else "")
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.get(url)
    if not r.is_success:
        error(f"list failed: HTTP {r.status_code}")
        sys.exit(1)
    rows = r.json()
    console.print(f"[bold]claims[/bold] total={len(rows)}")
    for c in rows:
        glyph = {"active": "[green]●[/green]", "completed": "[blue]✓[/blue]",
                 "blocked": "[yellow]⏸[/yellow]", "abandoned": "[red]✗[/red]"}.get(c["status"], "·")
        excl = "x" if c.get("exclusive") else "s"
        console.print(
            f"  {glyph} [{c['id'][:8]}] ({excl}) unit={c['unit']:<24} "
            f"agent={c['agent_id'][:8]}  intent={c.get('intent','')[:50]}"
        )


@orchestra.command(name="release")
@click.argument("claim_id")
async def release_cmd(claim_id: str) -> None:
    """Release a claim."""
    env = _need(*_REQUIRED)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.delete(f"{_base_url(env)}/sync/claims/{claim_id}")
    if r.status_code == 404:
        error(f"claim {claim_id} not found")
        sys.exit(1)
    if r.status_code not in (200, 204):
        error(f"release failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    console.print(f"[bold green]released[/bold green] [{claim_id[:8]}]")


@orchestra.command(name="claim-update")
@click.argument("claim_id")
@click.option("--status", type=click.Choice(["active", "blocked", "completed", "abandoned"]), default=None)
@click.option("--intent", default=None, help="Replace intent string")
@click.option("--extend-ttl-s", type=int, default=None, help="Bump TTL by this many seconds from now")
async def claim_update_cmd(
    claim_id: str, status: str | None, intent: str | None, extend_ttl_s: int | None
) -> None:
    """Update claim status / intent / TTL."""
    env = _need(*_REQUIRED)
    body: dict[str, Any] = {}
    if status:
        body["status"] = status
    if intent:
        body["intent"] = intent
    if extend_ttl_s is not None:
        body["extend_ttl_s"] = extend_ttl_s
    if not body:
        error("nothing to update — pass --status / --intent / --extend-ttl-s")
        sys.exit(2)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.patch(f"{_base_url(env)}/sync/claims/{claim_id}", json=body)
    if not r.is_success:
        error(f"update failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    c = r.json()
    console.print(f"[bold]updated[/bold] [{c['id'][:8]}] status={c['status']}")


# ── barriers ─────────────────────────────────────────────────────────


@orchestra.command(name="barrier-create")
@click.argument("name")
@click.argument("signals_required", type=int)
@click.option("--ttl-s", type=int, default=3600, help="Barrier TTL in seconds (60-86400)")
async def barrier_create_cmd(name: str, signals_required: int, ttl_s: int) -> None:
    """Create an N-of-N barrier. Returns the barrier id (use with barrier-signal)."""
    env = _need(*_REQUIRED)
    body = {"name": name, "signals_required": signals_required, "ttl_s": ttl_s}
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{_base_url(env)}/sync/barriers", json=body)
    if not r.is_success:
        error(f"barrier create failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    b = r.json()
    console.print(
        f"[bold green]barrier[/bold green] [{b['id'][:8]}] name={b['name']} "
        f"need={b['signals_required']} state={b['state']}"
    )


@orchestra.command(name="barrier-signal")
@click.argument("barrier_id")
async def barrier_signal_cmd(barrier_id: str) -> None:
    """Signal a barrier as this OA_AGENT. Opens it if signals_required is met."""
    env = _need(*_REQUIRED, "OA_AGENT")
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(
            f"{_base_url(env)}/sync/barriers/{barrier_id}/signal",
            json={"agent_id": env["OA_AGENT"]},
        )
    if r.status_code == 404:
        error(f"barrier {barrier_id} not found")
        sys.exit(1)
    if not r.is_success:
        error(f"signal failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    b = r.json()
    received = len(b.get("signals_received") or [])
    console.print(
        f"[bold]signaled[/bold] [{b['id'][:8]}] state={b['state']} "
        f"({received}/{b['signals_required']})"
    )


@orchestra.command(name="barrier-status")
@click.argument("barrier_id")
async def barrier_status_cmd(barrier_id: str) -> None:
    """Inspect a barrier's current state + signals received."""
    env = _need(*_REQUIRED)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.get(f"{_base_url(env)}/sync/barriers/{barrier_id}")
    if r.status_code == 404:
        error(f"barrier {barrier_id} not found")
        sys.exit(1)
    if not r.is_success:
        error(f"status failed: HTTP {r.status_code}")
        sys.exit(1)
    b = r.json()
    received = b.get("signals_received") or []
    console.print(
        f"[bold]barrier[/bold] [{b['id'][:8]}] name={b['name']} state={b['state']}\n"
        f"  required={b['signals_required']} received={len(received)}"
    )
    for s in received:
        console.print(f"    · {s}")


# ── locks ────────────────────────────────────────────────────────────


@orchestra.command(name="lock-acquire")
@click.argument("resource")
@click.option("--ttl-s", type=int, default=60, help="Lock TTL in seconds (1-86400)")
async def lock_acquire_cmd(resource: str, ttl_s: int) -> None:
    """Acquire a resource lock. Conflict (409) means another holder is active."""
    env = _need(*_REQUIRED, "OA_IDENT")
    body = {"resource": resource, "holder": env["OA_IDENT"], "ttl_s": ttl_s}
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{_base_url(env)}/sync/locks/acquire", json=body)
    if r.status_code == 409:
        error(f"already locked: {r.text[:200]}")
        sys.exit(3)
    if not r.is_success:
        error(f"acquire failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    lock = r.json()
    token = lock.get("token", "")
    console.print(
        f"[bold green]locked[/bold green] resource={resource}\n"
        f"  token={token}  (use this for release/renew; also exported as OA_LOCK_TOKEN)"
    )
    os.environ["OA_LOCK_TOKEN"] = token


@orchestra.command(name="lock-release")
@click.argument("resource")
@click.option("--token", default=None, help="Release token (defaults to $OA_LOCK_TOKEN)")
async def lock_release_cmd(resource: str, token: str | None) -> None:
    """Release a resource lock you hold."""
    env = _need(*_REQUIRED)
    tok = token or os.environ.get("OA_LOCK_TOKEN")
    if not tok:
        error("no token: pass --token or set OA_LOCK_TOKEN")
        sys.exit(2)
    body = {"resource": resource, "token": tok}
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{_base_url(env)}/sync/locks/release", json=body)
    if not r.is_success:
        error(f"release failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    console.print(f"[bold green]unlocked[/bold green] resource={resource}")


@orchestra.command(name="lock-renew")
@click.argument("resource")
@click.option("--token", default=None, help="Lock token (defaults to $OA_LOCK_TOKEN)")
@click.option("--ttl-s", type=int, default=60, help="New TTL in seconds (1-86400)")
async def lock_renew_cmd(resource: str, token: str | None, ttl_s: int) -> None:
    """Extend a held resource lock by ttl_s seconds."""
    env = _need(*_REQUIRED)
    tok = token or os.environ.get("OA_LOCK_TOKEN")
    if not tok:
        error("no token: pass --token or set OA_LOCK_TOKEN")
        sys.exit(2)
    body = {"resource": resource, "token": tok, "ttl_s": ttl_s}
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{_base_url(env)}/sync/locks/renew", json=body)
    if not r.is_success:
        error(f"renew failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    console.print(f"[bold]renewed[/bold] resource={resource} ttl_s={ttl_s}")


# ── shared knowledge ─────────────────────────────────────────────────
#
# Concerto.knowledge_space_ids is a list of space UUIDs that all
# participants treat as a shared collaboration surface (vs. each
# agent's private OA_KSPACE). Wired into:
#   - api/src/agent/loop_worker.py:220  (extra_space_ids for prompts)
#   - api/src/orchestra/routes/bootstrap.py:167 (bootstrap kits)
#   - api/src/mcp_info/server.py:139 (MCP tool exposure)
#
# `forktex … orchestra knowledge add` writes to the FIRST shared space
# (creating one if none exist + auto-attaching to the concerto).


async def _fetch_concerto_shared_spaces(env: dict[str, str]) -> list[str]:
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.get(f"{_base_url(env)}/concerto")
        if not r.is_success:
            error(f"concerto fetch failed: HTTP {r.status_code}")
            sys.exit(1)
        return list(r.json().get("knowledge_space_ids") or [])


async def _patch_concerto_spaces(env: dict[str, str], space_ids: list[str]) -> None:
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.patch(
            f"{_base_url(env)}/concerto", json={"knowledge_space_ids": space_ids}
        )
        if not r.is_success:
            error(f"concerto PATCH failed: HTTP {r.status_code} {r.text[:200]}")
            sys.exit(1)


async def _create_shared_space(env: dict[str, str], name: str) -> str:
    body = {"name": name, "description": "Auto-created shared space for concerto collaboration"}
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{env['OA_ENDPOINT']}/org/{env['OA_ORG']}/knowledge/spaces", json=body)
        if not r.is_success:
            error(f"create space failed: HTTP {r.status_code} {r.text[:200]}")
            sys.exit(1)
        return r.json()["id"]


@orchestra.group(name="knowledge")
def knowledge_group():
    """Shared-space writes & introspection (vs. ``push`` which is private)."""
    pass


@knowledge_group.command(name="add")
@click.argument("text")
@click.option("--tag", "tags", multiple=True, default=("shared",), help="Extra tag(s); 'orchestra'+ident always added")
@click.option("--kind", default="note", help="Knowledge entry kind (note/finding/analysis/recommendation)")
@click.option("--space-id", default=None, help="Target a specific shared space (defaults to first attached)")
async def knowledge_add_cmd(text: str, tags: tuple[str, ...], kind: str, space_id: str | None) -> None:
    """Push a knowledge entry to a shared concerto space (collaborative)."""
    env = _need(*_REQUIRED, "OA_IDENT")
    target = space_id
    if target is None:
        shared = await _fetch_concerto_shared_spaces(env)
        if not shared:
            error(
                "no shared spaces on this concerto. "
                "Run `forktex intelligence orchestra knowledge init-shared` first, "
                "or pass --space-id."
            )
            sys.exit(2)
        target = shared[0]
    body = {
        "kind": kind,
        "content_text": text,
        "space_id": target,
        "session_id": env["OA_SESSION"],
        "tags": ["orchestra", env["OA_IDENT"], *tags],
    }
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{env['OA_ENDPOINT']}/org/{env['OA_ORG']}/knowledge", json=body)
    if not r.is_success:
        error(f"shared push failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    eid = r.json().get("id", "?")
    console.print(f"[bold green]shared[/bold green] entry={eid} space={target[:8]}…")


@knowledge_group.command(name="spaces")
async def knowledge_spaces_cmd() -> None:
    """List the concerto's currently attached shared knowledge spaces."""
    env = _need(*_REQUIRED)
    shared = await _fetch_concerto_shared_spaces(env)
    if not shared:
        console.print("[yellow]no shared spaces attached to this concerto[/yellow]")
        return
    console.print(f"[bold]shared spaces[/bold] count={len(shared)}")
    for s in shared:
        console.print(f"  · {s}")


@knowledge_group.command(name="init-shared")
@click.option("--name", default=None, help="Space name (default: 'concerto-<sid8>-shared')")
async def knowledge_init_shared_cmd(name: str | None) -> None:
    """Ensure a shared space exists on this concerto (idempotent)."""
    env = _need(*_REQUIRED)
    shared = await _fetch_concerto_shared_spaces(env)
    if shared:
        console.print(f"[bold]already attached[/bold] count={len(shared)} first={shared[0][:8]}…")
        return
    sid_short = env["OA_SESSION"][:8]
    space_name = name or f"concerto-{sid_short}-shared"
    new_space = await _create_shared_space(env, space_name)
    await _patch_concerto_spaces(env, [new_space])
    console.print(
        f"[bold green]shared space ready[/bold green] name={space_name} id={new_space}"
    )


@knowledge_group.command(name="attach")
@click.argument("space_id")
async def knowledge_attach_cmd(space_id: str) -> None:
    """Attach an existing knowledge space to this concerto's shared list."""
    env = _need(*_REQUIRED)
    shared = await _fetch_concerto_shared_spaces(env)
    if space_id in shared:
        console.print(f"[yellow]already attached[/yellow] {space_id}")
        return
    shared.append(space_id)
    await _patch_concerto_spaces(env, shared)
    console.print(f"[bold green]attached[/bold green] {space_id}  total={len(shared)}")


# ── attach ────────────────────────────────────────────────────────────


async def do_attach(
    ident: str,
    *,
    org_id: str | None = None,
    from_path: str | None = None,
    no_hello: bool = False,
) -> dict[str, str]:
    """Bind OA_* into this process, send hello + heartbeat. Return the env dict.

    Public helper so callers (the bare ``forktex`` REPL, programmatic
    bootstraps) can attach without going through Click. ``attach_cmd`` is
    a thin wrapper.
    """
    path, d = _load_stash(ident, from_path)
    env = _stash_to_env(ident, d, org_id)
    os.environ.update(env)

    base = _base_url(env)
    headers = _headers(env)

    pushed_id: str | None = None
    if not no_hello:
        hello_body = {
            "kind": "note",
            "content_text": f"hello from {ident}, attached via forktex CLI",
            "space_id": env["OA_KSPACE"],
            "session_id": env["OA_SESSION"],
            "tags": ["orchestra", ident, "hello"],
        }
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            r = await client.post(
                f"{env['OA_ENDPOINT']}/org/{env['OA_ORG']}/knowledge",
                json=hello_body,
            )
        if r.is_success:
            pushed_id = r.json().get("id")
        else:
            error(f"hello push failed: HTTP {r.status_code} {r.text[:200]}")
            sys.exit(1)

    async with httpx.AsyncClient(timeout=5.0, headers=headers) as client:
        rb = await client.post(
            f"{base}/participants/{env['OA_PARTICIPANT']}/heartbeat", json={}
        )
    if rb.status_code not in (200, 204):
        error(f"heartbeat failed: HTTP {rb.status_code}")
        sys.exit(1)

    console.print(
        f"[bold green]attached[/bold green]  ident={ident}  "
        f"session={env['OA_SESSION'][:8]}…  stash={path}"
    )
    if pushed_id:
        console.print(f"  hello entry={pushed_id}  ♥")
    else:
        console.print("  ♥")
    return env


@orchestra.command(name="attach")
@click.argument("ident")
@click.option("--org-id", default=None, help="Org UUID (defaults to env or first matching bootstrap)")
@click.option("--from", "from_path", default=None, help="Explicit path to a bootstrap JSON (overrides cache search)")
@click.option("--no-hello", is_flag=True, help="Skip the one-shot hello push (heartbeat still sent)")
async def attach_cmd(
    ident: str, org_id: str | None, from_path: str | None, no_hello: bool
) -> None:
    """Bind OA_* into this process, send hello + heartbeat, return.

    Unlike ``resume`` (which prints eval-ready exports for a parent shell),
    ``attach`` mutates ``os.environ`` of the *current* Python process. Inside
    the bare ``forktex`` REPL this means subsequent ``orchestra`` commands
    in the same session can run with no further setup.

    Usage::

        forktex intelligence orchestra attach forktex-py-dev
    """
    await do_attach(ident, org_id=org_id, from_path=from_path, no_hello=no_hello)


# ── consensus: decisions + votes ──────────────────────────────────────


@orchestra.command(name="propose")
@click.argument("question")
@click.option("--strategy", type=click.Choice(["majority", "unanimous", "first"]), default="majority")
@click.option("--choice", "choices", multiple=True, help="Allowed choice (repeat); omit for free-form")
async def propose_cmd(question: str, strategy: str, choices: tuple[str, ...]) -> None:
    """Propose a concerto decision (requires concerto:write)."""
    env = _need(*_REQUIRED)
    body: dict[str, Any] = {"question": question, "strategy": strategy}
    if choices:
        body["choices"] = list(choices)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(f"{_base_url(env)}/concerto/decisions", json=body)
    if r.status_code == 403:
        error(f"forbidden: {r.text[:200]} — your key likely lacks concerto:write")
        sys.exit(3)
    if not r.is_success:
        error(f"propose failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    d = r.json()
    console.print(
        f"[bold green]proposed[/bold green] {d['id']}\n  "
        f"strategy={d.get('strategy')} status={d.get('status')}\n  Q: {d.get('question','')[:100]}"
    )


@orchestra.command(name="vote")
@click.argument("decision_id")
@click.argument("choice")
@click.option("--weight", type=float, default=1.0)
@click.option("--rationale", default=None, help="Optional vote rationale")
async def vote_cmd(decision_id: str, choice: str, weight: float, rationale: str | None) -> None:
    """Cast a vote on a concerto decision (requires concerto:vote:cast)."""
    env = _need(*_REQUIRED)
    body: dict[str, Any] = {"choice": choice, "weight": weight}
    if rationale:
        body["rationale"] = rationale
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.post(
            f"{_base_url(env)}/concerto/decisions/{decision_id}/vote", json=body
        )
    if r.status_code == 404:
        error(f"decision {decision_id} not found")
        sys.exit(1)
    if not r.is_success:
        error(f"vote failed: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    d = r.json()
    votes = d.get("votes") or []
    console.print(
        f"[bold green]voted[/bold green] [{d['id'][:8]}] choice={choice!r} "
        f"status={d.get('status')} ({len(votes)} vote(s))"
        + (f"\n  → resolution={d.get('resolution')!r}" if d.get("resolution") else "")
    )


@orchestra.command(name="decisions")
@click.option("--status", default=None, help="Filter: open|resolved")
async def decisions_cmd(status: str | None) -> None:
    """List concerto decisions in this session."""
    env = _need(*_REQUIRED)
    async with httpx.AsyncClient(timeout=10.0, headers=_headers(env)) as client:
        r = await client.get(f"{_base_url(env)}/concerto/decisions")
    if not r.is_success:
        error(f"list failed: HTTP {r.status_code}")
        sys.exit(1)
    rows = r.json()
    if status:
        rows = [d for d in rows if d.get("status") == status]
    console.print(f"[bold]decisions[/bold] total={len(rows)}")
    for d in rows:
        glyph = "[blue]✓[/blue]" if d.get("status") == "resolved" else "[yellow]·[/yellow]"
        votes = d.get("votes") or []
        console.print(
            f"  {glyph} [{d['id'][:8]}] strategy={d.get('strategy'):<10} "
            f"status={d.get('status'):<10} votes={len(votes)}\n"
            f"      Q: {d.get('question','')[:90]}"
            + (f"\n      → {d.get('resolution')}" if d.get("resolution") else "")
        )


def _extract_org(d: dict) -> str | None:
    """Best-effort: parse org from any URL-like field."""
    import re
    for key in ("endpoint",):
        v = d.get(key, "")
        m = re.search(r"/org/([0-9a-f-]{36})/", v)
        if m:
            return m.group(1)
    return None


def known_idents() -> list[str]:
    """List idents with a stashed bootstrap JSON across cached dirs.

    Used by the bare-``forktex`` REPL to detect when a user's free-form
    prompt mentions an orchestra ident — so it can suggest ``attach``.
    """
    import pathlib

    seen: list[str] = []
    for d in _CACHE_DIRS:
        try:
            for p in pathlib.Path(d).glob("*.json"):
                stem = p.stem
                if stem not in seen:
                    seen.append(stem)
        except OSError:
            continue
    return seen


__all__ = ["orchestra", "known_idents", "do_attach"]
