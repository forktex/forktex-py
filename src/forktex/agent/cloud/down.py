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

"""forktex cloud down — tear down (remote or local dev)."""

from __future__ import annotations

import subprocess
import sys

import asyncclick as click


@click.command()
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--keep-dns", is_flag=True, help="Keep DNS records")
@click.option(
    "--env", "environment", default=None, help="Environment (local for local teardown)"
)
@click.pass_context
async def down(ctx, yes, keep_dns, environment):
    """Tear down: destroy server + DNS (remote) or stop containers (local)."""
    if environment == "local":
        from forktex_cloud import paths as _cloud_paths

        project_root = ctx.obj["project_root"]
        compose_file = str(_cloud_paths.compose_path(project_root, "local"))

        # Resolve project name from manifest for compose isolation
        project_name = "forktex"
        try:
            from forktex_cloud.manifest.loader import Manifest

            manifest = Manifest.load(project_root / "forktex.json", env="local")
            project_name = manifest.name or "forktex"
        except FileNotFoundError, ValueError, KeyError:
            click.echo(
                f"Warning: could not load manifest, using project name '{project_name}'",
                err=True,
            )

        result = subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                project_name,
                "-f",
                compose_file,
                "down",
                "-v",
                "--remove-orphans",
            ],
        )
        if result.returncode != 0:
            sys.exit(result.returncode)
        return

    if not yes:
        click.confirm("This will tear down the deployment. Continue?", abort=True)

    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()
    project_root = ctx.obj["project_root"]

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        click.echo(f"Running down pipeline via {cloud_ctx.controller}...")
        result = client.down(
            keep_dns=keep_dns,
            project_dir=project_root,
        )
        click.echo(f"Down pipeline complete: {result.status}")
