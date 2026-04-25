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

"""forktex cloud vault — hybrid: local vault or remote API."""

from __future__ import annotations

import asyncclick as click


@click.group()
@click.pass_context
async def vault(ctx):
    """Manage encrypted secrets."""
    pass


def _resolve_mode(ctx) -> str:
    """Determine local vs remote vault mode."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    return "remote" if cloud_ctx.is_connected else "local"


@vault.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--env", default="default", help="Target environment")
@click.pass_context
async def vault_set(ctx, key, value, env):
    """Store a secret value."""
    mode = _resolve_mode(ctx)

    if mode == "remote":
        cloud_ctx = ctx.obj["cloud_ctx"]
        from forktex_cloud.client import ForktexCloudClient

        with ForktexCloudClient.from_context(cloud_ctx) as client:
            client.vault_set(key, value, env=env)
    else:
        project_root = ctx.obj["project_root"]
        from forktex_cloud.secrets.factory import get_secrets_provider

        provider = get_secrets_provider(project_root=project_root)
        provider.set(key, value, env)

    click.echo(f"Secret '{key}' stored (env={env})")


@vault.command("get")
@click.argument("key")
@click.option("--env", default="default", help="Target environment")
@click.pass_context
async def vault_get(ctx, key, env):
    """Retrieve a secret value."""
    mode = _resolve_mode(ctx)

    if mode == "remote":
        cloud_ctx = ctx.obj["cloud_ctx"]
        from forktex_cloud.client import ForktexCloudClient

        with ForktexCloudClient.from_context(cloud_ctx) as client:
            result = client.vault_get(key, env=env)
            click.echo(result.value or "")
    else:
        project_root = ctx.obj["project_root"]
        from forktex_cloud.secrets.factory import get_secrets_provider

        try:
            provider = get_secrets_provider(project_root=project_root)
            click.echo(provider.get(key, env))
        except KeyError as e:
            raise click.ClickException(str(e))


@vault.command("list")
@click.option("--env", default="default", help="Target environment")
@click.pass_context
async def vault_list(ctx, env):
    """List all secret keys."""
    mode = _resolve_mode(ctx)

    if mode == "remote":
        cloud_ctx = ctx.obj["cloud_ctx"]
        from forktex_cloud.client import ForktexCloudClient

        with ForktexCloudClient.from_context(cloud_ctx) as client:
            keys = client.vault_list(env=env)
    else:
        project_root = ctx.obj["project_root"]
        from forktex_cloud.secrets.factory import get_secrets_provider

        provider = get_secrets_provider(project_root=project_root)
        keys = provider.list_keys(env)

    if not keys:
        click.echo("(no secrets)")
    for k in keys:
        click.echo(k)


@vault.command("delete")
@click.argument("key")
@click.option("--env", default="default", help="Target environment")
@click.pass_context
async def vault_delete(ctx, key, env):
    """Remove a secret."""
    mode = _resolve_mode(ctx)

    if mode == "remote":
        cloud_ctx = ctx.obj["cloud_ctx"]
        from forktex_cloud.client import ForktexCloudClient

        with ForktexCloudClient.from_context(cloud_ctx) as client:
            client.vault_delete(key, env=env)
    else:
        project_root = ctx.obj["project_root"]
        from forktex_cloud.secrets.factory import get_secrets_provider

        provider = get_secrets_provider(project_root=project_root)
        provider.delete(key, env)

    click.echo(f"Secret '{key}' deleted (env={env})")
