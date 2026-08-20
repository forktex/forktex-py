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
from forktex.agent.cloud.errors import translate_cloud_errors


@click.command()
@click.option("--project", "project_id", default=None, help="Filter by project ID")
@click.option("--limit", default=20, help="Number of events to show (default: 20)")
@click.pass_context
@translate_cloud_errors
async def events(ctx, project_id, limit):
    """View audit events for the connected org."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud import Cloud

    with Cloud.from_context(cloud_ctx) as client:
        items = client.list_audit_events(limit=limit, project_id=project_id)

    if not items:
        click.echo("No events.")
        return

    for ev in items:
        ts = ""
        created = getattr(ev, "createdAt", None) or getattr(ev, "created_at", None)
        if created is not None:
            try:
                ts = created.isoformat(timespec="seconds")
            except (AttributeError, TypeError):
                ts = str(created)[:19]
        action = getattr(ev, "action", None) or "?"
        status = getattr(ev, "status", None) or "?"
        details = getattr(ev, "details", None) or ""
        if status == "success":
            status_str = click.style(status, fg="green")
        elif status == "failed":
            status_str = click.style(status, fg="red")
        else:
            status_str = click.style(status, fg="yellow")
        click.echo(f"  {ts}  {action:<10s}  {status_str:<18s}  {details}")
