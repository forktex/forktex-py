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

"""forktex cloud ssl — SSL status (read-only). Provisioning happens inside `forktex cloud up`."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.group()
async def ssl(ctx=None):
    """SSL certificate status. Certificates are provisioned automatically by `forktex cloud up`."""


@ssl.command("status")
@click.argument("server_id")
@click.pass_context
@translate_cloud_errors
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
            icon = (
                click.style("✓", fg="green") if enabled else click.style("✗", fg="red")
            )
            click.echo(
                f"  {icon}  SSL {'enabled' if enabled else 'disabled'}  domain={domain}  expires={expires}"
            )
        else:
            click.echo("  SSL status not available (server may not be provisioned yet)")
