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

"""forktex cloud deploy — deploy to a server (remote)."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.command()
@click.argument("server_id")
@click.option("--service", default=None, help="Deploy a single service by ID")
@click.option("--tags", default=None, help="Comma-separated Ansible tags")
@click.option("--env", "environment", default=None, help="Environment overlay")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.pass_context
@translate_cloud_errors
async def deploy(ctx, server_id, service, tags, environment, verbose):
    """Push a new release to one of your cloud servers."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    project_root = ctx.obj["project_root"]
    tag_list = tags.split(",") if tags else None
    with ForktexCloudClient.from_context(cloud_ctx) as client:
        click.echo(f"Deploying to {server_id}...")
        result = client.deploy(
            server_id,
            tags=tag_list,
            service=service,
            project_dir=project_root,
        )
        click.echo(f"Deploy triggered: {result.status}")
