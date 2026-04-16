"""forktex cloud deploy — deploy to a server (remote)."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.argument("server_id")
@click.option("--service", default=None, help="Deploy a single service by ID")
@click.option("--tags", default=None, help="Comma-separated Ansible tags")
@click.option("--env", "environment", default=None, help="Environment overlay")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.pass_context
async def deploy(ctx, server_id, service, tags, environment, verbose):
    """Deploy to a server via the cloud controller."""
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
