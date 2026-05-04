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

"""forktex cloud server — VPS management (remote)."""

from __future__ import annotations

import asyncclick as click


@click.group()
@click.pass_context
async def server(ctx):
    """VPS server management."""
    pass


@server.command("list")
@click.pass_context
async def server_list(ctx):
    """List servers."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        servers = client.list_servers()

    if not servers:
        click.echo("No servers.")
        return

    fmt = "  {:<38s}  {:<24s}  {:<16s}  {:<12s}  {}"
    click.echo(fmt.format("ID", "NAME", "IP", "PROVIDER", "STATUS"))
    for s in servers:
        click.echo(
            fmt.format(
                str(s.id),
                s.name,
                s.ipv4 or "-",
                s.provider,
                s.status,
            )
        )


@server.command("create")
@click.option("--name", required=True, help="Server name")
@click.option(
    "--flavour", default=None, help="Flavour (starter/standard/performance/heavy)"
)
@click.option("--region", default=None, help="Region")
@click.option("--type", "server_type", default=None, help="Server type override")
@click.option("--image", default=None, help="OS image")
@click.option("--location", default=None, help="Data center override")
@click.option("--project", "project_id", default="", help="Project name")
@click.pass_context
async def server_create(
    ctx, name, flavour, region, server_type, image, location, project_id
):
    """Create a new VPS."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.create_server(
            name,
            flavour=flavour,
            region=region,
            server_type=server_type,
            image=image,
            location=location,
            project_id=project_id,
        )
    click.echo(result.model_dump_json(indent=2))


@server.command("show")
@click.argument("server_id")
@click.pass_context
async def server_show(ctx, server_id):
    """Show server details."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        srv = client.get_server(server_id)
    click.echo(srv.model_dump_json(indent=2))


@server.command("destroy")
@click.argument("server_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
async def server_destroy(ctx, server_id, yes):
    """Destroy a VPS."""
    if not yes:
        click.confirm(f"Destroy server {server_id}?", abort=True)

    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.destroy_server(server_id)
    click.echo(f"Server {server_id} destroyed: {result.status}")


@server.command("restart")
@click.argument("server_id")
@click.option("--service", default=None, help="Restart a single service by name")
@click.pass_context
async def server_restart_cmd(ctx, server_id, service):
    """Restart services on a server."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.server_restart(server_id, service=service)
    click.echo(f"Restart: {result.status}")
    if result.output:
        click.echo(result.output)


@server.command("exec")
@click.argument("server_id")
@click.option("--service", required=True, help="Service/container name")
@click.argument("command")
@click.pass_context
async def server_exec_cmd(ctx, server_id, service, command):
    """Execute a command inside a service container."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.server_exec(server_id, service=service, command=command)
    click.echo(result.output or result.status)


@server.command("switch")
@click.argument("server_id")
@click.option(
    "--component", required=True, help="Compute service id to flip (e.g. 'web', 'api')."
)
@click.option(
    "--to-color",
    required=True,
    type=click.Choice(["blue", "green"]),
    help="Target slot to make active.",
)
@click.pass_context
async def server_switch_cmd(ctx, server_id, component, to_color):
    """Manually switch blue-green traffic for a component (manual rollback path)."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.server_switch(server_id, component=component, to_color=to_color)
    click.echo(f"Switch {component} -> {to_color}: {result.status}")
    if result.output:
        click.echo(result.output)


@server.command("update")
@click.argument("server_id")
@click.option("--component", required=True, help="Compute service id to update.")
@click.option("--new-image", required=True, help="New docker image (e.g. 'myapi:v2').")
@click.pass_context
async def server_update_cmd(ctx, server_id, component, new_image):
    """Blue-green image update: pull, deploy to inactive slot, health check, auto-switch.

    If the new slot fails health checks the old slot keeps traffic —
    i.e. auto-rollback on deploy failure.
    """
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.server_update(
            server_id, component=component, new_image=new_image
        )
    click.echo(f"Update {component} -> {new_image}: {result.status}")
    if result.output:
        click.echo(result.output)


@server.command("import")
@click.option("--name", required=True, help="Server name")
@click.option("--host", required=True, help="IP address or hostname")
@click.option("--user", default="root", help="SSH user (default: root)")
@click.option("--project", "project_id", default=None, help="Project ID")
@click.pass_context
async def server_import_cmd(ctx, name, host, user, project_id):
    """Import an existing VPS (BYOVPS)."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.import_server(name, host, user=user, project_id=project_id)
    click.echo(result.model_dump_json(indent=2))
