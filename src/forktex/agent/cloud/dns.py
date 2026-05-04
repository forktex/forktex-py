# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""forktex cloud dns — DNS status (read-only). Provisioning happens inside `forktex cloud up`."""

from __future__ import annotations

import asyncclick as click


@click.group()
async def dns(ctx=None):
    """DNS status. DNS records are provisioned automatically by `forktex cloud up`."""


@dns.command("verify")
@click.argument("domain")
@click.pass_context
async def dns_verify(ctx, domain):
    """Check if a domain resolves (client-side DNS lookup)."""
    import socket

    try:
        addrs = socket.getaddrinfo(domain, None)
        ips = sorted(set(addr[4][0] for addr in addrs))
        click.echo(f"  ✓  {domain} → {', '.join(ips)}")
    except socket.gaierror:
        raise click.ClickException(f"DNS not propagated for {domain} — try again in a few minutes")


@dns.command("status")
@click.argument("server_id")
@click.pass_context
async def dns_status(ctx, server_id):
    """Show DNS records for a server (from server status)."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        status = client.server_status(server_id)
        dns_records = status.get("dns", []) if isinstance(status, dict) else []
        if dns_records:
            for rec in dns_records:
                click.echo(f"  {rec}")
        else:
            ip = status.get("serverIp", "") if isinstance(status, dict) else ""
            click.echo(f"  server ip: {ip}")
            click.echo("  (detailed DNS records available in Cloudflare dashboard)")
