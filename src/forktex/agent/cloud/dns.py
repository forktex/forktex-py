"""forktex cloud dns — DNS management (remote)."""

from __future__ import annotations

import asyncclick as click


@click.group()
@click.pass_context
async def dns(ctx):
    """DNS management."""
    pass


@dns.command("setup")
@click.argument("server_id")
@click.option("--domain", required=True, help="Domain to point at the server")
@click.pass_context
async def dns_setup(ctx, server_id, domain):
    """Set up DNS records for a server."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    click.echo(f"Setting up DNS: {domain} -> server {server_id}")
    click.echo("(DNS setup is handled server-side during deploy)")


@dns.command("verify")
@click.option("--domain", required=True, help="Domain to check")
@click.pass_context
async def dns_verify(ctx, domain):
    """Verify DNS propagation."""
    import socket

    try:
        addrs = socket.getaddrinfo(domain, None)
        ips = sorted(set(addr[4][0] for addr in addrs))
        click.echo(f"DNS verified: {domain} resolves to {', '.join(ips)}")
    except socket.gaierror:
        raise click.ClickException(f"DNS not yet propagated for {domain}")
