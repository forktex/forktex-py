"""forktex cloud events — view deployment events and history."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.option("--project", "project_id", default=None, help="Filter by project ID")
@click.option("--limit", default=20, help="Number of events to show (default: 20)")
@click.pass_context
async def events(ctx, project_id, limit):
    """View deployment events and history."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        items = client.list_events(project_id=project_id)

    if not items:
        click.echo("No events.")
        return

    items = items[:limit]
    for ev in items:
        ts = ev.created_at.isoformat(timespec="seconds") if ev.created_at else ""
        action = ev.action or "?"
        status = ev.status or "?"
        details = ev.details or ""
        # Colorize status
        if status == "success":
            status_str = click.style(status, fg="green")
        elif status == "failed":
            status_str = click.style(status, fg="red")
        else:
            status_str = click.style(status, fg="yellow")
        click.echo(f"  {ts}  {action:<10s}  {status_str:<18s}  {details}")
