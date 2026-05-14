# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""forktex cloud dns — DNS status (read-only). Provisioning happens inside `forktex cloud up`."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.group()
async def dns(ctx=None):
    """DNS status. DNS records are provisioned automatically by `forktex cloud up`."""


@dns.command("verify")
@click.argument("domain")
@click.pass_context
@translate_cloud_errors
async def dns_verify(ctx, domain):
    """Check if a domain resolves (client-side DNS lookup)."""
    import socket

    try:
        addrs = socket.getaddrinfo(domain, None)
        ips = sorted(set(addr[4][0] for addr in addrs))
        click.echo(f"  ✓  {domain} → {', '.join(ips)}")
    except socket.gaierror:
        raise click.ClickException(
            f"DNS not propagated for {domain} — try again in a few minutes"
        )


@dns.command("status")
@click.argument("server_id")
@click.pass_context
@translate_cloud_errors
async def dns_status(ctx, server_id):
    """Show DNS records for a server (from server status)."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud import Cloud

    with Cloud.from_context(cloud_ctx) as client:
        status = client.server_status(server_id)
        dns_records = status.get("dns", []) if isinstance(status, dict) else []
        if dns_records:
            for rec in dns_records:
                click.echo(f"  {rec}")
        else:
            ip = status.get("serverIp", "") if isinstance(status, dict) else ""
            click.echo(f"  server ip: {ip}")
            click.echo("  (detailed DNS records available in Cloudflare dashboard)")
