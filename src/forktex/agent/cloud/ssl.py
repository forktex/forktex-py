"""forktex cloud ssl — SSL certificate management (remote)."""

from __future__ import annotations

import asyncclick as click


@click.group()
@click.pass_context
async def ssl(ctx):
    """SSL certificate management."""
    pass


@ssl.command("provision")
@click.option("--domain", required=True, help="Domain for the certificate")
@click.option("--email", default=None, help="Email for Let's Encrypt")
@click.option("--dns", "use_dns", is_flag=True, help="Use DNS-01 challenge")
@click.option("--dry-run", is_flag=True, help="Test without issuing")
@click.pass_context
async def ssl_provision(ctx, domain, email, use_dns, dry_run):
    """Provision a certificate (server-side)."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    click.echo(f"Requesting SSL certificate for {domain}...")
    click.echo("(Certificate provisioning is handled server-side during deploy)")


@ssl.command("list")
@click.pass_context
async def ssl_list(ctx):
    """List certificates."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    click.echo("(Certificate listing available via server status)")


@ssl.command("import")
@click.option("--domain", required=True, help="Domain")
@click.option("--cert", required=True, help="Path to certificate file")
@click.option("--key", required=True, help="Path to private key file")
@click.pass_context
async def ssl_import(ctx, domain, cert, key):
    """Import a custom certificate."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    click.echo(f"Importing certificate for {domain}...")
    click.echo("(Certificate import is handled server-side)")
