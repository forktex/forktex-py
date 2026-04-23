"""forktex cloud usage — view org VPS-hours and cost."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.option(
    "--months",
    type=int,
    default=0,
    help="Show N months of history (default: current only)",
)
@click.pass_context
async def usage(ctx, months):
    """View current month VPS-hours + cost for your org.

    Usage is retroactive: the platform tallies what happened and bills
    at month-end. No pre-payment gates.
    """
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        params = {"months": months} if months else {}
        resp = client._check(
            client._client.get(f"{client._org_prefix}/usage", params=params)
        )
        data = resp.json()

    current = data.get("current", {})
    click.echo(f"Usage for org {current.get('org_id', '?')}")
    click.echo(
        f"  Period: {current.get('period_start', '?')[:10]} — {current.get('period_end', '?')[:10]}"
    )
    click.echo(
        f"  VPS-hours: {current.get('totalVpsHours', current.get('total_vps_hours', 0)):.1f}"
    )
    click.echo(
        f"  Cost:      {current.get('totalCost', current.get('total_cost', 0)):.2f}"
    )
    click.echo(
        f"  Active:    {current.get('activeServerCount', current.get('active_server_count', 0))} server(s)"
    )

    servers = current.get("servers", [])
    if servers:
        click.echo()
        fmt = "    {:<38s} {:<12s} {:>8s} {:>8s}"
        click.echo(fmt.format("SERVER", "TYPE", "HOURS", "COST"))
        for s in servers:
            click.echo(
                fmt.format(
                    s.get("server_name", "?"),
                    s.get("server_type", "-") or "-",
                    f"{s.get('hours', 0):.1f}",
                    f"{s.get('cost', 0):.2f}",
                )
            )

    history = data.get("history", [])
    if history:
        click.echo()
        click.echo("History:")
        for h in history:
            click.echo(
                f"  {h.get('period_start', '?')[:7]}  "
                f"{h.get('vps_hours', 0):.1f} hours  "
                f"{h.get('cost', 0):.2f} cost  "
                f"{h.get('server_count', 0)} servers"
            )
