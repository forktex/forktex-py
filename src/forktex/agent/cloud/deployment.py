# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""forktex cloud deployment — list, cancel, and retry deployments."""

from __future__ import annotations

import asyncclick as click


@click.group("deployment")
def deployment():
    """Inspect and control deployments (list / cancel / retry)."""


@deployment.command("list")
@click.option("--status", default=None, help="Filter by status (started, success, failed, cancelled)")
@click.option("--limit", default=20, show_default=True, help="Max results")
@click.pass_context
async def deployment_list(ctx, status, limit):
    """List recent deployments for the connected org."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        items = client.list_org_deployments(status=status, limit=limit)

    if not items:
        click.echo("  (no deployments found)")
        return

    click.echo(f"  {'ID':38s} {'Status':12s} {'Env':36s} Started")
    click.echo(f"  {'─' * 100}")
    for d in items:
        did = d.get("id", "?")[:36]
        st = d.get("status", "?")
        env = (d.get("environmentId") or d.get("environment_id") or "?")[:36]
        started = (d.get("startedAt") or d.get("started_at") or "?")[:19]
        color = {"success": "green", "failed": "red", "cancelled": "yellow", "started": "cyan"}.get(st, "white")
        click.echo(f"  {did:38s} {click.style(st, fg=color):20s} {env:38s} {started}")


@deployment.command("cancel")
@click.argument("deployment_id")
@click.pass_context
async def deployment_cancel(ctx, deployment_id):
    """Cancel a running deployment."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.cancel_deployment(deployment_id)

    click.echo(f"  {click.style('✓', fg='yellow')} Deployment {deployment_id[:8]}… cancelled")


@deployment.command("retry")
@click.argument("deployment_id")
@click.pass_context
async def deployment_retry(ctx, deployment_id):
    """Re-dispatch a failed or cancelled deployment."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.retry_deployment(deployment_id)

    new_id = getattr(result, "deployment_id", "?")
    click.echo(f"  {click.style('✓', fg='green')} Retried as deployment {new_id}")
    click.echo(f"  Watch: forktex cloud logs")
