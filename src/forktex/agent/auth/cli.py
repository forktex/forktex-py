# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Per-service ``connect`` / ``disconnect`` command factories + the top-level
``forktex status`` aggregator.

Each service owns the pair under its own click group — there is no separate
``forktex auth`` surface. All three services share the same verb names and
option set so the experience of connecting to cloud, intelligence, and
network is literally the same muscle memory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Awaitable, Callable, Optional

import asyncclick as click
from rich.prompt import Prompt
from rich.table import Table

from forktex.agent.auth.status import collect_auth_status
from forktex.agent.auth.store import clear as store_clear
from forktex.agent.auth.types import FACETS, Facet
from forktex.agent.ui.console import console, error, info, success


def _project_root(project: Optional[str]) -> Path:
    return Path(project).resolve() if project else Path.cwd()


# ── verbose connect-error reporter (shared by cloud / intelligence / network) ─


_DEFAULT_ENDPOINTS = {
    "cloud": "https://cloud.forktex.com",
    "intelligence": "https://intelligence.forktex.com/api",
    "network": "https://network.forktex.com",
}
_LOCAL_HINTS = {
    "cloud": "http://localhost:8000  (forktex-cloud dev stack)",
    "intelligence": "http://localhost:8002  (forktex-intelligence dev stack)",
    "network": "http://localhost:9000  (forktex-network dev stack)",
}


def _classify(exc: BaseException) -> tuple[Optional[int], Optional[str]]:
    """Extract (status_code, detail) from whatever API-error shape a service
    SDK raises. Returns (None, None) if this isn't a recognisable HTTP error."""
    status = getattr(exc, "status_code", None)
    detail = getattr(exc, "detail", None)
    if status is None:
        # Fall back to parsing `HTTP 404: …` from str(exc).
        s = str(exc)
        if s.startswith("HTTP "):
            try:
                after = s[5:]
                code_part, rest = after.split(":", 1)
                status = int(code_part.strip())
                detail = rest.strip()
            except Exception:
                pass
    return status, detail


def _render_connect_error(service: str, url: str, exc: BaseException) -> None:
    import httpx

    default = _DEFAULT_ENDPOINTS.get(service, "")
    local = _LOCAL_HINTS.get(service, "")
    status, detail = _classify(exc)

    console.print()
    error(f"{service} connect failed")
    console.print(f"  [bold]endpoint:[/bold] [cyan]{url or '—'}[/cyan]")
    if status is not None:
        console.print(f"  [bold]status:[/bold]   {status}")
    if detail:
        # Keep body short; rich will wrap.
        snippet = detail if len(detail) <= 240 else detail[:237] + "…"
        console.print(f"  [bold]body:[/bold]     {snippet}")
    else:
        console.print(f"  [bold]error:[/bold]    {exc.__class__.__name__}: {exc}")

    # Targeted hint based on failure class.
    hint_lines: list[str] = []
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        hint_lines.append(f"Cannot reach {url}. Is the controller running?")
        if url != default:
            hint_lines.append(f"Default is {default}. Local dev: {local}.")
    elif status == 404:
        hint_lines.append(
            f"The URL is reachable but has no {service} API at that path."
        )
        if url == default:
            hint_lines.append(
                f"{default} may not be live yet — point at a local stack with "
                f"--endpoint {local.split()[0] if local else '<url>'}."
            )
        else:
            hint_lines.append(f"Check the base URL; default is {default}.")
    elif status in (401, 403):
        hint_lines.append("Credentials were rejected.")
        if service in ("intelligence", "network"):
            hint_lines.append(
                "If you don't have an account yet, pass --new to register."
            )
        else:
            hint_lines.append(
                "Cloud accounts are created at https://forktex.com/signup."
            )
    elif status and 500 <= status < 600:
        hint_lines.append(f"Server error at {url}. Retry; if it persists, report it.")
    elif status == 422:
        hint_lines.append(
            "The server rejected the payload (likely wrong email/password format)."
        )

    for line in hint_lines:
        console.print(f"  [dim]→ {line}[/dim]")
    console.print()


# ── top-level `forktex status` ───────────────────────────────────────────────


@click.command(name="status")
@click.option("--project", "-d", default=None, help="Project directory")
@click.option("--no-probe", is_flag=True, help="Skip reachability checks (offline).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
async def status_cmd(project, no_probe, as_json):
    """Quick overview: are you signed in to Cloud, Intelligence, and Network?"""
    root = _project_root(project)
    states = await collect_auth_status(root, probe=not no_probe)

    if as_json:
        out = {
            facet: {
                "configured": s.configured,
                "endpoint": s.endpoint,
                "principal": s.principal,
                "auth_kind": s.auth_kind,
                "scope": s.scope,
                "source_path": str(s.source_path) if s.source_path else None,
                "reachable": s.reachable,
                "error": s.error,
                "detail": s.detail,
            }
            for facet, s in states.items()
        }
        console.print_json(json.dumps(out))
        return

    # Project + environment header (formerly `forktex info`).
    import sys

    from forktex.agent.ui.display import CLI_VERSION

    console.print(
        f"[bold]ForkTex[/bold] [dim]v{CLI_VERSION}[/dim]   "
        f"project: [cyan]{root}[/cyan]   "
        f"python: [dim]{sys.version.split()[0]}[/dim]   "
        f"platform: [dim]{sys.platform}[/dim]"
    )
    console.print()

    table = Table(title="forktex status", show_lines=False)
    table.add_column("Facet", style="bold")
    table.add_column("State")
    table.add_column("Endpoint", overflow="fold")
    table.add_column("Kind")
    table.add_column("Scope")
    table.add_column("Principal / detail", overflow="fold")

    for facet in FACETS:
        s = states[facet]
        if not s.configured:
            table.add_row(facet, "[dim]✗ not set[/dim]", "—", "—", "—", "—")
            continue
        state_cell = "[green]✓ configured[/green]"
        if s.reachable is True:
            state_cell = "[green]✓ reachable[/green]"
        elif s.reachable is False:
            state_cell = f"[yellow]⚠ unreachable[/yellow] {s.error or ''}"
        detail_bits = [s.principal] if s.principal else []
        detail_bits += [f"{k}={v}" for k, v in s.detail.items()]
        table.add_row(
            facet,
            state_cell,
            s.endpoint or "—",
            s.auth_kind or "—",
            s.scope or "—",
            ", ".join(detail_bits) or "—",
        )
    console.print(table)


# ── per-facet command factories ──────────────────────────────────────────────


def build_facet_commands(
    facet: Facet,
    connect_impl: Callable[..., Awaitable[None]],
) -> tuple[click.Command, click.Command]:
    """Return ``(connect, disconnect)`` click commands for *facet*.

    Each service group calls this, so the credential verbs are identical
    across cloud, intelligence, and network. Operational ``status`` commands
    are service-specific and live in each module; the top-level
    :func:`status_cmd` aggregates credential state across all three.
    """

    @click.command(name="connect")
    @click.option("--project", "-d", default=None, help="Project directory")
    @click.option(
        "--global",
        "save_global",
        is_flag=True,
        help="Save to ~/.forktex/ instead of the project.",
    )
    @click.option(
        "--endpoint",
        "--url",
        "endpoint",
        default=None,
        help="Service endpoint / controller URL.",
    )
    @click.option("--email", default=None, help="Account email.")
    @click.option(
        "--password", default=None, help="Account password (prompts if omitted)."
    )
    @click.option(
        "--api-key",
        default=None,
        help="API key for CI/CD capture (cloud: ftx-…, intelligence: sk-…).",
    )
    @click.option(
        "--new",
        "new_account",
        is_flag=True,
        help="Intelligence/network: register a new account instead of connecting to an existing one.",
    )
    async def connect_cmd(
        project, save_global, endpoint, email, password, api_key, new_account
    ):
        """Connect this service — login, or register if the account doesn't exist."""
        await connect_impl(
            project=project,
            save_global=save_global,
            endpoint=endpoint,
            email=email,
            password=password,
            api_key=api_key,
            new_account=new_account,
        )

    @click.command(name="disconnect")
    @click.option("--project", "-d", default=None, help="Project directory")
    @click.option(
        "--global",
        "clear_global",
        is_flag=True,
        help="Clear the global file instead of the project one.",
    )
    async def disconnect_cmd(project, clear_global):
        """Remove saved credentials for this service at the chosen scope."""
        root = None if clear_global else _project_root(project)
        scope = "global" if clear_global else "project"
        path = store_clear(facet, scope, root)
        success(f"disconnected from {facet} @ {scope}: {path}")

    return connect_cmd, disconnect_cmd


# ── per-service connect implementations (reused by cloud / intelligence / network) ─


async def connect_cloud(
    *, project, save_global, endpoint, email, password, api_key, new_account
):
    from forktex.agent.cloud.settings import save_cloud_context_global
    from forktex.cloud import (
        Cloud,
        CloudContext,
    )  # `Cloud` is the canonical (and only) SDK client name.

    url = endpoint or Prompt.ask("Controller URL", default="https://cloud.forktex.com")
    url = url.rstrip("/")

    if new_account:
        info(
            "cloud accounts are created at https://forktex.com/signup. "
            "Once the account exists, run `forktex cloud connect` (or `/connect cloud`)."
        )
        return

    if api_key:
        ctx = CloudContext(controller=url, account_key=api_key)
        save_cloud_context_global(ctx)
        try:
            with Cloud(url, account_key=api_key) as client:
                client.health()
            success(f"cloud: saved api_key for {url}")
        except Exception as exc:
            click.echo(f"saved, but could not verify: {exc}", err=True)
        return

    email = email or Prompt.ask("Email")
    password = password or Prompt.ask("Password", password=True)

    try:
        with Cloud(url) as client:
            token_resp = client.login(email, password)
            access_token = token_resp.accessToken
            with Cloud(url, access_token=access_token) as authed:
                orgs = authed.list_orgs()
            if not orgs:
                error("no organizations for this account.")
                sys.exit(1)
            if len(orgs) == 1:
                org = orgs[0]
            else:
                click.echo("\nAvailable organizations:")
                for i, o in enumerate(orgs, 1):
                    click.echo(f"  {i}. {o.name} ({o.slug})")
                choice = click.prompt(
                    "Select organization", type=click.IntRange(1, len(orgs)), default=1
                )
                org = orgs[choice - 1]
            with Cloud(url) as client:
                region = client.health().region
    except Exception as exc:
        _render_connect_error("cloud", url, exc)
        sys.exit(1)

    ctx = CloudContext(
        controller=url,
        access_token=access_token,
        org_id=str(org.id),
        region=region,
    )
    save_cloud_context_global(ctx)
    success(f"cloud: connected as {email} → {org.name} ({org.slug})")


async def connect_intelligence(
    *, project, save_global, endpoint, email, password, api_key, new_account
):
    from forktex.agent.intelligence.settings import (
        save_intelligence_global,
        save_intelligence_project,
    )
    from forktex.intelligence import Intelligence, IntelligenceSettings

    url = endpoint or Prompt.ask(
        "API endpoint", default="https://intelligence.forktex.com/api"
    )

    if api_key:
        key = api_key
    else:
        email = email or Prompt.ask("Email")
        password = password or Prompt.ask("Password", password=True)
        # Bootstrap phase: we don't have an API key yet (we're about to
        # create one). `Intelligence()` requires api_key to be non-empty,
        # so pass a placeholder — the `/auth/login` and `/auth/register`
        # endpoints don't validate it. Once we have the real key we
        # re-construct Intelligence with it for verification.
        intel = Intelligence(endpoint=url, api_key="bootstrap")
        try:
            if new_account:
                await intel.register(email, password)
            else:
                try:
                    await intel.login(email, password)
                except Exception:
                    await intel.register(email, password)
            # Org discovery: `Intelligence.me()` returns user + orgs in
            # one round-trip. The list-orgs / create-api-key verbs live
            # on the underlying client (exposed via `intel.client`) — we
            # access them through the facade so the only `forktex_*`
            # symbol forktex-py imports is `Intelligence` itself.
            orgs = await intel.client.list_orgs()
            if not orgs:
                error("no orgs for this account.")
                sys.exit(1)
            org_id = orgs[0]["id"]
            intel.set_org(org_id)
            key_resp = await intel.client.create_api_key("forktex-cli")
            key = key_resp.get("raw_key", "")
        except Exception as exc:
            await intel.close()
            _render_connect_error("intelligence", url, exc)
            sys.exit(1)
        await intel.close()
        if not key:
            error("intelligence: server did not return an API key.")
            sys.exit(1)

    settings = IntelligenceSettings(endpoint=url, api_key=key)
    try:
        async with Intelligence(endpoint=url, api_key=key) as verify:
            health = await verify.health()
        info(f"verified: intelligence v{getattr(health, 'version', '?')}")
    except Exception as exc:
        info(f"saved, but verification failed: {exc}")

    if save_global:
        save_intelligence_global(settings)
        success(f"intelligence: saved globally → {url}")
    else:
        root = _project_root(project)
        save_intelligence_project(settings, str(root))
        success(f"intelligence: saved to {root}/.forktex/intelligence.json")


async def connect_network(
    *, project, save_global, endpoint, email, password, api_key, new_account
):
    from datetime import datetime, timezone

    # `NetWork` is the canonical name; falls back to `NetworkClient`
    # on older SDK floors. The forktex-py shim handles the alias.
    from forktex.network import (
        NetWork,
        NetworkSettings,
        save_network_global,
        save_network_project,
    )

    if api_key:
        error("network does not support API keys yet; use email/password to connect.")
        sys.exit(2)

    url = endpoint or Prompt.ask(
        "Network base URL", default="https://network.forktex.com"
    )
    url = url.rstrip("/")
    email = email or Prompt.ask("Email")
    password = password or Prompt.ask("Password", password=True)

    client = NetWork(base_url=url)
    try:
        if new_account:
            token = await client.register(email, password)
        else:
            try:
                token = await client.login(email, password)
            except Exception:
                token = await client.register(email, password)
    except Exception as exc:
        await client.close()
        _render_connect_error("network", url, exc)
        sys.exit(1)
    await client.close()

    settings = NetworkSettings(
        endpoint=url,
        jwt_token=token.jwt_token,
        principal_email=email,
        authenticated_at=datetime.now(timezone.utc).isoformat(),
    )

    if save_global:
        save_network_global(settings)
        success(f"network: saved globally → {url}")
    else:
        root = _project_root(project)
        save_network_project(settings, root)
        success(f"network: saved to {root}/.forktex/network.json")
