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

"""forktex cloud registry — manage artifact registry credentials."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.group()
def registry():
    """Manage artifact registry credentials (Harbor, GHCR, Docker Hub)."""


@registry.command("list")
@click.pass_context
@translate_cloud_errors
async def registry_list(ctx):
    """List all registered artifact registries."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        regs = client.list_registries()
        if not regs:
            click.echo("  No registries registered.")
            return
        for r in regs:
            verified = (
                click.style("✓", fg="green")
                if getattr(r, "verifiedAt", None)
                else click.style("○", fg="yellow")
            )
            click.echo(
                f"  {verified}  {getattr(r, 'id', '?')}  "
                f"{getattr(r, 'name', '?'):20}  {getattr(r, 'type', '?'):12}  "
                f"{getattr(r, 'url', '?')}"
            )


@registry.command("add")
@click.option("--name", required=True, help="Friendly name for this registry")
@click.option(
    "--url", required=True, help="Registry base URL (e.g. https://registry.example.com)"
)
@click.option("--user", required=True, help="Username or robot account")
@click.option("--password", required=True, help="Password or token")
@click.option(
    "--type",
    "reg_type",
    type=click.Choice(["harbor", "ghcr", "dockerhub", "generic"]),
    default="generic",
    help="Registry type (default: generic)",
)
@click.pass_context
@translate_cloud_errors
async def registry_add(ctx, name, url, user, password, reg_type):
    """Register an artifact registry.

    \b
    Examples:
        forktex cloud registry add --name harbor \\
            --url https://registry.example.com \\
            --user robot\\$myproject \\
            --password <token> --type harbor

        forktex cloud registry add --name ghcr \\
            --url https://ghcr.io \\
            --user myorg --password <pat> --type ghcr
    """
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        reg = client.add_registry(
            name=name,
            type=reg_type,
            url=url,
            username=user,
            password=password,
        )
        click.echo(f"  ✓  registry registered: {getattr(reg, 'name', name)}")
        click.echo(
            f"     id={getattr(reg, 'id', '?')}  type={getattr(reg, 'type', reg_type)}"
        )

        # Auto-verify after adding
        reg_id = str(getattr(reg, "id", ""))
        if reg_id:
            result = client.verify_registry(reg_id)
            verified = getattr(result, "verified", False)
            detail = getattr(result, "detail", "")
            if verified:
                click.echo(f"     {click.style('verified ✓', fg='green')}")
            else:
                click.echo(
                    f"     {click.style('verification failed (check URL/credentials)', fg='yellow')}: {detail}"
                )


@registry.command("verify")
@click.argument("registry_id")
@click.pass_context
@translate_cloud_errors
async def registry_verify(ctx, registry_id):
    """Test connectivity for a registry credential."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.verify_registry(registry_id)
        verified = getattr(result, "verified", False)
        detail = getattr(result, "detail", "")
        if verified:
            click.echo(f"  {click.style('✓ verified', fg='green')}  {detail}")
        else:
            click.echo(f"  {click.style('✗ failed', fg='red')}  {detail}")


@registry.command("remove")
@click.argument("registry_id")
@click.pass_context
@translate_cloud_errors
async def registry_remove(ctx, registry_id):
    """Remove a registry credential."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        client.delete_registry(registry_id)
        click.echo(f"  ✓  registry {registry_id[:8]}… removed")
