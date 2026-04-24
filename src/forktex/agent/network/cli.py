"""``forktex network`` command group — V1 exposes ``status`` only."""

from __future__ import annotations

from pathlib import Path

import asyncclick as click

from forktex.agent.network.client_factory import build_network_client
from forktex.agent.network.settings import load_network_settings
from forktex.agent.ui.console import console, error, info


@click.group()
async def network():
    """ForkTex Network — projects, tasks, worklogs, channels.

    Credentials are captured via ``forktex network login``.
    """
    pass


@network.command(name="status")
@click.option("--project", "-d", default=None, help="Project directory")
async def status_cmd(project):
    """Show Network connection state and round-trip ``identity_me``."""
    root = Path(project).resolve() if project else Path.cwd()
    settings = load_network_settings(project_root=root)

    console.print(f"[bold]Endpoint:[/bold] {settings.endpoint or '[dim]not set[/dim]'}")
    console.print(
        f"[bold]Principal:[/bold] {settings.principal_email or '[dim]not set[/dim]'}"
    )
    console.print(
        f"[bold]Authenticated at:[/bold] {settings.authenticated_at or '[dim]unknown[/dim]'}"
    )

    if not settings.is_configured:
        info("Not configured. Run: forktex network login")
        return

    client = build_network_client(settings)
    try:
        me = await client.identity_me()
        console.print(f"[bold green]Status:[/bold green] OK — me: {me.email}")
    except Exception as exc:
        error(f"identity_me failed: {exc}")
    finally:
        await client.close()


# Credential verbs (login / logout) — shared shape with cloud & intelligence.
from forktex.agent.auth import build_facet_commands, login_network as _login_network

_network_login, _network_logout = build_facet_commands("network", _login_network)
network.add_command(_network_login)
network.add_command(_network_logout)
