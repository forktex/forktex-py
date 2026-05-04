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

"""``forktex network`` command group — V1 exposes ``status`` only."""
# ruff: noqa: E402

from __future__ import annotations

from pathlib import Path

import asyncclick as click

from forktex.agent.network.client_factory import build_network_client
from forktex.agent.network.settings import load_network_settings
from forktex.agent.ui.console import console, error, info


@click.group()
async def network():
    """ForkTex Network — projects, tasks, worklogs, channels.

    Credentials are captured via ``forktex network connect``.
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
        info("Not configured. Run: forktex network connect")
        return

    client = build_network_client(settings)
    try:
        me = await client.identity_me()
        console.print(f"[bold green]Status:[/bold green] OK — me: {me.email}")
    except Exception as exc:
        error(f"identity_me failed: {exc}")
    finally:
        await client.close()


# Credential verbs (connect / disconnect) — shared shape with cloud & intelligence.
from forktex.agent.auth import build_facet_commands, connect_network as _connect_network

_network_connect, _network_disconnect = build_facet_commands(
    "network", _connect_network
)
network.add_command(_network_connect)
network.add_command(_network_disconnect)
