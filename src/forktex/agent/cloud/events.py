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
