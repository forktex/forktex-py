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

"""forktex cloud status — show server status (remote)."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.argument("server_id", required=False, default=None)
@click.pass_context
async def status(ctx, server_id):
    """Show server status and health. Uses active server if ID not given."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    server_id = server_id or cloud_ctx.current_server
    if not server_id:
        raise click.ClickException("No server ID given and no active server set. Run: forktex cloud use server <id>")

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.server_status(server_id)

    click.echo(
        f"Server: {result.get('server_name', server_id)} ({result.get('server_ip', '?')})"
    )
    click.echo()
    click.echo("Containers:")
    for c in result.get("containers", []):
        click.echo(
            f"  {c.get('name', ''):30s}  {c.get('state', ''):10s}  {c.get('status', '')}"
        )
    click.echo()
    click.echo("Health probes:")
    for name, code in result.get("health", {}).items():
        click.echo(f"  {name:30s}  {code}")
