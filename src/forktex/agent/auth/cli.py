"""Per-facet ``login`` / ``logout`` command factories + the top-level
``forktex status`` aggregator.

Each facet owns the pair under its own click group — there is no separate
``forktex auth`` surface. All three facets share the same verb names and the
same option set so the experience of connecting to cloud, intelligence, and
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
from forktex.agent.auth.store import load_state
from forktex.agent.auth.types import FACETS, Facet
from forktex.agent.ui.console import console, error, info, success


def _project_root(project: Optional[str]) -> Path:
    return Path(project).resolve() if project else Path.cwd()


# ── top-level `forktex status` ───────────────────────────────────────────────


@click.command(name="status")
@click.option("--project", "-d", default=None, help="Project directory")
@click.option("--no-probe", is_flag=True, help="Skip reachability checks (offline).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
async def status_cmd(project, no_probe, as_json):
    """Aggregate status table across cloud, intelligence, and network."""
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
    login_impl: Callable[..., Awaitable[None]],
) -> tuple[click.Command, click.Command]:
    """Return ``(login, logout)`` click commands for *facet*.

    Each facet group calls this, so the credential verbs are identical across
    cloud, intelligence, and network. Operational ``status`` commands are
    facet-specific and live in each facet module; the top-level
    :func:`status_cmd` aggregates credential state across all three.
    """

    @click.command(name="login")
    @click.option("--project", "-d", default=None, help="Project directory")
    @click.option("--global", "save_global", is_flag=True, help="Save to ~/.forktex/ instead of the project.")
    @click.option("--endpoint", "--url", "endpoint", default=None, help="Facet endpoint / controller URL.")
    @click.option("--email", default=None, help="Account email.")
    @click.option("--password", default=None, help="Account password (prompts if omitted).")
    @click.option("--api-key", default=None, help="API key for CI/CD capture (cloud: ftx-…, intelligence: sk-…).")
    @click.option("--new-account", is_flag=True, help="Intelligence/network: register instead of logging in.")
    async def login_cmd(project, save_global, endpoint, email, password, api_key, new_account):
        """Authenticate with this facet and save credentials."""
        await login_impl(
            project=project,
            save_global=save_global,
            endpoint=endpoint,
            email=email,
            password=password,
            api_key=api_key,
            new_account=new_account,
        )

    @click.command(name="logout")
    @click.option("--project", "-d", default=None, help="Project directory")
    @click.option("--global", "clear_global", is_flag=True, help="Clear the global file instead of the project one.")
    async def logout_cmd(project, clear_global):
        """Remove saved credentials for this facet at the chosen scope."""
        root = None if clear_global else _project_root(project)
        scope = "global" if clear_global else "project"
        path = store_clear(facet, scope, root)
        success(f"logged out of {facet} @ {scope}: {path}")

    return login_cmd, logout_cmd


# ── per-facet login implementations (reused by cloud / intelligence / network) ─


async def login_cloud(*, project, save_global, endpoint, email, password, api_key, new_account):
    from forktex.agent.cloud.settings import save_cloud_context_global
    from forktex_cloud.client import ForktexCloudClient
    from forktex_cloud.config import CloudContext

    url = endpoint or Prompt.ask("Controller URL", default="https://cloud.forktex.com")
    url = url.rstrip("/")

    if api_key:
        ctx = CloudContext(controller=url, account_key=api_key)
        save_cloud_context_global(ctx)
        try:
            with ForktexCloudClient(url, account_key=api_key) as client:
                client.health()
            success(f"cloud: saved api_key for {url}")
        except Exception as exc:
            click.echo(f"saved, but could not verify: {exc}", err=True)
        return

    email = email or Prompt.ask("Email")
    password = password or Prompt.ask("Password", password=True)

    try:
        with ForktexCloudClient(url) as client:
            token_resp = client.login(email, password)
            access_token = token_resp.access_token
            with ForktexCloudClient(url, access_token=access_token) as authed:
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
                choice = click.prompt("Select organization", type=click.IntRange(1, len(orgs)), default=1)
                org = orgs[choice - 1]
            with ForktexCloudClient(url) as client:
                region = client.health().region
    except Exception as exc:
        error(f"cloud login failed: {exc}")
        sys.exit(1)

    ctx = CloudContext(
        controller=url,
        access_token=access_token,
        org_id=str(org.id),
        region=region,
    )
    save_cloud_context_global(ctx)
    success(f"cloud: logged in as {email} → {org.name} ({org.slug})")


async def login_intelligence(*, project, save_global, endpoint, email, password, api_key, new_account):
    from forktex.agent.intelligence.settings import save_intelligence_global, save_intelligence_project
    from forktex_intelligence.client.client import ForktexIntelligenceClient
    from forktex_intelligence.config import IntelligenceSettings

    url = endpoint or Prompt.ask("API endpoint", default="https://intelligence.forktex.com/api")

    if api_key:
        key = api_key
    else:
        email = email or Prompt.ask("Email")
        password = password or Prompt.ask("Password", password=True)
        client = ForktexIntelligenceClient(url)
        try:
            if new_account:
                await client.register(email, password)
            else:
                try:
                    await client.login(email, password)
                except Exception:
                    await client.register(email, password)
            orgs = await client.list_orgs()
            if not orgs:
                error("no orgs for this account.")
                sys.exit(1)
            org_id = orgs[0]["id"]
            client.set_org(org_id)
            key_resp = await client.create_api_key("forktex-cli")
            key = key_resp.get("raw_key", "")
        except Exception as exc:
            await client.close()
            error(f"intelligence auth failed: {exc}")
            sys.exit(1)
        await client.close()
        if not key:
            error("intelligence: server did not return an API key.")
            sys.exit(1)

    settings = IntelligenceSettings(endpoint=url, api_key=key)
    try:
        verify_client = ForktexIntelligenceClient(url, key)
        health = await verify_client.health()
        await verify_client.close()
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


async def login_network(*, project, save_global, endpoint, email, password, api_key, new_account):
    from datetime import datetime, timezone

    from forktex_network import NetworkClient

    from forktex.agent.network.settings import (
        NetworkSettings,
        save_network_global,
        save_network_project,
    )

    if api_key:
        error("network does not support API keys yet; use email/password login.")
        sys.exit(2)

    url = endpoint or Prompt.ask("Network base URL", default="https://network.forktex.com")
    url = url.rstrip("/")
    email = email or Prompt.ask("Email")
    password = password or Prompt.ask("Password", password=True)

    client = NetworkClient(base_url=url)
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
        error(f"network auth failed: {exc}")
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
