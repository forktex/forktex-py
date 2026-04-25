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

"""forktex cloud project — project namespace operations (remote)."""

from __future__ import annotations

import asyncclick as click


@click.group()
@click.pass_context
async def project(ctx):
    """Project management."""
    pass


@project.command("list")
@click.pass_context
async def project_list(ctx):
    """List projects."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        projects = client.list_projects()

    if not projects:
        click.echo("No projects.")
        return
    for p in projects:
        click.echo(f"  {p.id}  {p.name}")


@project.command("create")
@click.option("--name", required=True, help="Project name")
@click.option("--manifest", default=None, help="Manifest path")
@click.option("--id", "project_id", default=None, help="Custom project ID")
@click.pass_context
async def project_create(ctx, name, manifest, project_id):
    """Create a project."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.create_project(name, manifest=manifest, project_id=project_id)
    click.echo(result.model_dump_json(indent=2))


@project.command("show")
@click.option("--id", "project_id", required=True, help="Project ID")
@click.pass_context
async def project_show(ctx, project_id):
    """Show project details."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        proj = client.get_project(project_id)
    click.echo(proj.model_dump_json(indent=2))
