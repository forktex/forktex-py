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
