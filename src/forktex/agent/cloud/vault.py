# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""forktex cloud vault — hybrid: local vault or remote API."""

from __future__ import annotations

import asyncclick as click


@click.group()
@click.pass_context
async def vault(ctx):
    """Manage encrypted secrets."""
    pass


def _resolve_mode(ctx) -> str:
    cloud_ctx = ctx.obj["cloud_ctx"]
    return "remote" if cloud_ctx.is_connected else "local"


def _resolve_env_id(client, cloud_ctx, env_name: str | None) -> str | None:
    """Resolve an environment name or UUID to an environment UUID.

    Resolution order:
      1. If env_name looks like a UUID, use it directly.
      2. If cloud_ctx.current_environment is set and env_name is None/default, use it.
      3. Look up by name across the active project's environments.
    """
    import uuid as _uuid

    # None / "default" → no scope (global vault)
    if not env_name or env_name == "default":
        if cloud_ctx.current_environment:
            return cloud_ctx.current_environment
        return None

    # Already a UUID?
    try:
        _uuid.UUID(env_name)
        return env_name
    except ValueError:
        pass

    # Look up by name from the active project
    project_id = cloud_ctx.current_project
    if not project_id:
        # Try to find by name across all projects
        projects = client.list_projects()
        for p in projects:
            envs = client.list_project_environments(str(p.id))
            for e in envs:
                if getattr(e, "name", None) == env_name:
                    return str(e.id)
        raise click.ClickException(
            f"Environment {env_name!r} not found. "
            "Run `forktex cloud use project <name>` first, or pass a UUID."
        )

    envs = client.list_project_environments(project_id)
    for e in envs:
        if getattr(e, "name", None) == env_name:
            return str(e.id)

    raise click.ClickException(f"Environment {env_name!r} not found in active project.")


@vault.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--env", default=None, help="Environment name or UUID (default: active context env)")
@click.pass_context
async def vault_set(ctx, key, value, env):
    """Store a secret value."""
    mode = _resolve_mode(ctx)

    if mode == "remote":
        cloud_ctx = ctx.obj["cloud_ctx"]
        from forktex_cloud.client import ForktexCloudClient

        with ForktexCloudClient.from_context(cloud_ctx) as client:
            env_id = _resolve_env_id(client, cloud_ctx, env)
            client.vault_set(key, value, environment_id=env_id)
    else:
        project_root = ctx.obj["project_root"]
        from forktex_cloud.secrets.factory import get_secrets_provider
        provider = get_secrets_provider(project_root=project_root)
        provider.set(key, value, env or "default")

    env_label = env or "(global)"
    click.echo(f"  ✓  {key}  [{env_label}]")


@vault.command("get")
@click.argument("key")
@click.option("--env", default=None, help="Environment name or UUID")
@click.pass_context
async def vault_get(ctx, key, env):
    """Retrieve a secret value."""
    mode = _resolve_mode(ctx)

    if mode == "remote":
        cloud_ctx = ctx.obj["cloud_ctx"]
        from forktex_cloud.client import ForktexCloudClient

        with ForktexCloudClient.from_context(cloud_ctx) as client:
            env_id = _resolve_env_id(client, cloud_ctx, env)
            result = client.vault_get(key, environment_id=env_id)
            click.echo(result.value or "")
    else:
        project_root = ctx.obj["project_root"]
        from forktex_cloud.secrets.factory import get_secrets_provider
        try:
            provider = get_secrets_provider(project_root=project_root)
            click.echo(provider.get(key, env or "default"))
        except KeyError as e:
            raise click.ClickException(str(e))


@vault.command("list")
@click.option("--env", default=None, help="Environment name or UUID")
@click.pass_context
async def vault_list(ctx, env):
    """List all secret keys."""
    mode = _resolve_mode(ctx)

    if mode == "remote":
        cloud_ctx = ctx.obj["cloud_ctx"]
        from forktex_cloud.client import ForktexCloudClient

        with ForktexCloudClient.from_context(cloud_ctx) as client:
            env_id = _resolve_env_id(client, cloud_ctx, env)
            keys = client.vault_list(environment_id=env_id)
    else:
        project_root = ctx.obj["project_root"]
        from forktex_cloud.secrets.factory import get_secrets_provider
        provider = get_secrets_provider(project_root=project_root)
        keys = provider.list_keys(env or "default")

    if not keys:
        click.echo("  (no secrets)")
    for k in keys:
        click.echo(f"  {k}")


@vault.command("delete")
@click.argument("key")
@click.option("--env", default=None, help="Environment name or UUID")
@click.pass_context
async def vault_delete(ctx, key, env):
    """Remove a secret."""
    mode = _resolve_mode(ctx)

    if mode == "remote":
        cloud_ctx = ctx.obj["cloud_ctx"]
        from forktex_cloud.client import ForktexCloudClient

        with ForktexCloudClient.from_context(cloud_ctx) as client:
            env_id = _resolve_env_id(client, cloud_ctx, env)
            client.vault_delete(key, environment_id=env_id)
    else:
        project_root = ctx.obj["project_root"]
        from forktex_cloud.secrets.factory import get_secrets_provider
        provider = get_secrets_provider(project_root=project_root)
        provider.delete(key, env or "default")

    click.echo(f"  ✓  deleted {key}")
