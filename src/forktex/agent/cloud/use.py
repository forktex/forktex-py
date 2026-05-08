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

# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""forktex cloud use — switch active context (org / project / env / server)."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.group()
async def use():
    """Switch the active context for subsequent commands.

    Stores the selection in ~/.forktex/cloud.json so that commands like
    ``forktex cloud logs``, ``forktex cloud status``, ``forktex cloud vault list``
    can resolve defaults without explicit IDs.

    \b
    Examples:
        forktex cloud use org my-org
        forktex cloud use project my-app
        forktex cloud use env staging
        forktex cloud use server 0f848b6e
        forktex cloud use show
    """


@use.command(name="org")
@click.argument("slug_or_id")
@click.pass_context
@translate_cloud_errors
async def use_org(ctx, slug_or_id):
    """Switch the active organisation."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient
    from forktex.agent.cloud.settings import save_cloud_context_global

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        orgs = client.list_orgs()

    match = _find(orgs, slug_or_id, ["id", "slug", "orgId"])
    if not match:
        raise click.ClickException(f"Org not found: {slug_or_id!r}")

    org_id = str(getattr(match, "id", None) or getattr(match, "orgId", ""))
    cloud_ctx.org_id = org_id
    save_cloud_context_global(cloud_ctx)
    click.echo(
        click.style(
            f"  ✓  active org → {getattr(match, 'slug', slug_or_id)}  [{org_id[:8]}]",
            fg="green",
        )
    )


@use.command(name="project")
@click.argument("name_or_id")
@click.pass_context
@translate_cloud_errors
async def use_project(ctx, name_or_id):
    """Switch the active project."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()
    project_root = ctx.obj["project_root"]

    from forktex_cloud.client import ForktexCloudClient
    from forktex.agent.cloud.settings import save_cloud_context_project

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        projects = client.list_projects()

    match = _find(projects, name_or_id, ["id", "name", "projectId"])
    if not match:
        raise click.ClickException(f"Project not found: {name_or_id!r}")

    project_id = str(getattr(match, "id", None) or getattr(match, "projectId", ""))
    cloud_ctx.current_project = project_id
    cloud_ctx.current_environment = None
    cloud_ctx.current_server = None
    save_cloud_context_project(cloud_ctx, project_root)
    click.echo(
        click.style(
            f"  ✓  active project → {getattr(match, 'name', name_or_id)}  [{project_id[:8]}]",
            fg="green",
        )
    )


@use.command(name="env")
@click.argument("name_or_id")
@click.pass_context
@translate_cloud_errors
async def use_env(ctx, name_or_id):
    """Switch the active environment (requires active project)."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()
    project_root = ctx.obj["project_root"]

    project_id = cloud_ctx.current_project
    if not project_id:
        raise click.ClickException(
            "No active project. Run: forktex cloud use project <name>"
        )

    from forktex_cloud.client import ForktexCloudClient
    from forktex.agent.cloud.settings import save_cloud_context_project

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        envs = client.list_project_environments(project_id)

    match = _find(envs, name_or_id, ["id", "name", "environmentId"])
    if not match:
        raise click.ClickException(f"Environment not found: {name_or_id!r}")

    env_id = str(getattr(match, "id", None) or getattr(match, "environmentId", ""))
    cloud_ctx.current_environment = env_id
    save_cloud_context_project(cloud_ctx, project_root)
    click.echo(
        click.style(
            f"  ✓  active env → {getattr(match, 'name', name_or_id)}  [{env_id[:8]}]",
            fg="green",
        )
    )


@use.command(name="server")
@click.argument("id_or_ip")
@click.pass_context
@translate_cloud_errors
async def use_server(ctx, id_or_ip):
    """Switch the active server."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()
    project_root = ctx.obj["project_root"]

    from forktex_cloud.client import ForktexCloudClient
    from forktex.agent.cloud.settings import save_cloud_context_project

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        servers = client.list_servers()

    match = _find(servers, id_or_ip, ["id", "ip", "ipv4", "name", "serverId"])
    if not match:
        raise click.ClickException(f"Server not found: {id_or_ip!r}")

    server_id = str(getattr(match, "id", None) or getattr(match, "serverId", ""))
    cloud_ctx.current_server = server_id
    save_cloud_context_project(cloud_ctx, project_root)
    s_name = getattr(match, "name", id_or_ip)
    s_ip = getattr(match, "ip", None) or getattr(match, "ipv4", "")
    click.echo(
        click.style(
            f"  ✓  active server → {s_name}  {s_ip}  [{server_id[:8]}]", fg="green"
        )
    )


@use.command(name="show")
@click.pass_context
@translate_cloud_errors
async def use_show(ctx):
    """Show the current active context."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    click.echo()
    click.echo(click.style("  Active context:", bold=True))
    click.echo(f"  controller:   {cloud_ctx.controller or '(not set)'}")
    click.echo(f"  org_id:       {cloud_ctx.org_id or '(not set)'}")
    click.echo(f"  project:      {cloud_ctx.current_project or '(not set)'}")
    click.echo(f"  environment:  {cloud_ctx.current_environment or '(not set)'}")
    click.echo(f"  server:       {cloud_ctx.current_server or '(not set)'}")
    click.echo()


def _find(items, query: str, fields: list[str]):
    """Find an item by matching query against any of the given fields."""
    query_lower = query.lower()
    for item in items:
        for f in fields:
            val = getattr(item, f, None)
            if val is not None and (
                str(val) == query
                or str(val).lower() == query_lower
                or str(val).startswith(query)
            ):
                return item
    return None
