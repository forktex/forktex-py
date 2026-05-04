# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""forktex cloud ssl — SSL status (read-only). Provisioning happens inside `forktex cloud up`."""

from __future__ import annotations

import asyncclick as click


@click.group()
async def ssl(ctx=None):
    """SSL certificate status. Certificates are provisioned automatically by `forktex cloud up`."""


@ssl.command("status")
@click.argument("server_id")
@click.pass_context
async def ssl_status(ctx, server_id):
    """Show SSL certificate status for a server."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        status = client.server_status(server_id)
        ssl_info = status.get("ssl", {}) if isinstance(status, dict) else {}
        if ssl_info:
            enabled = ssl_info.get("enabled", False)
            domain = ssl_info.get("domain", "")
            expires = ssl_info.get("expiresAt", "unknown")
            icon = click.style("✓", fg="green") if enabled else click.style("✗", fg="red")
            click.echo(f"  {icon}  SSL {'enabled' if enabled else 'disabled'}  domain={domain}  expires={expires}")
        else:
            click.echo("  SSL status not available (server may not be provisioned yet)")
