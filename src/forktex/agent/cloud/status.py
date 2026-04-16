"""forktex cloud status — show server status (remote)."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.argument("server_id")
@click.pass_context
async def status(ctx, server_id):
    """Show server status and health."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.server_status(server_id)

    click.echo(f"Server: {result.get('server_name', server_id)} ({result.get('server_ip', '?')})")
    click.echo()
    click.echo("Containers:")
    for c in result.get("containers", []):
        click.echo(f"  {c.get('name', ''):30s}  {c.get('state', ''):10s}  {c.get('status', '')}")
    click.echo()
    click.echo("Health probes:")
    for name, code in result.get("health", {}).items():
        click.echo(f"  {name:30s}  {code}")
