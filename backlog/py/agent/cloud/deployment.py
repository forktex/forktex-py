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

"""forktex cloud deployment — inspect recent flow runs (the unit of deployment)."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.group("deployment")
def deployment():
    """Inspect and control deployments (list / cancel / retry)."""


@deployment.command("list")
@click.option(
    "--status",
    default=None,
    help="Filter by status (started, success, failed, cancelled)",
)
@click.option("--limit", default=20, show_default=True, help="Max results")
@click.pass_context
@translate_cloud_errors
async def deployment_list(ctx, status, limit):
    """List recent flow runs (deploys, destroys, backups, restores) for the connected org."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud import Cloud

    with Cloud.from_context(cloud_ctx) as client:
        items = client.list_flow_runs(status=status, limit=limit)

    if not items:
        click.echo("  (no flow runs found)")
        return

    click.echo(f"  {'RUN ID':38s} {'PIPELINE':28s} {'STATUS':12s} STARTED")
    click.echo(f"  {'─' * 100}")
    for run in items:
        run_id = (run.get("runId") or run.get("run_id") or "?")[:36]
        pipeline = (run.get("pipeline") or run.get("name") or "?")[:26]
        st = run.get("status", "?")
        started = (run.get("startedAt") or run.get("started_at") or "?")[:19]
        color = {
            "completed": "green",
            "failed": "red",
            "cancelled": "yellow",
            "running": "cyan",
        }.get(st, "white")
        click.echo(
            f"  {run_id:38s} {pipeline:28s} {click.style(st, fg=color):20s} {started}"
        )


@deployment.command("cancel")
@click.argument("run_id")
@click.pass_context
@translate_cloud_errors
async def deployment_cancel(ctx, run_id):
    """Cancel a running flow run (deploy in progress)."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud import Cloud

    with Cloud.from_context(cloud_ctx) as client:
        # The API exposes /api/org/{org_id}/flows/{run_id}/cancel — no SDK
        # wrapper yet; use the raw httpx escape hatch. Re-wrap once
        # `Cloud.cancel_flow_run` lands in a future SDK release.
        client._check(
            client._client.post(f"{client._org_prefix}/flows/{run_id}/cancel")
        )

    click.echo(
        f"  {click.style('✓', fg='yellow')} Flow run {run_id[:8]}… cancellation requested"
    )


@deployment.command("retry")
@click.argument("run_id")
@click.pass_context
@translate_cloud_errors
async def deployment_retry(ctx, run_id):
    """Re-dispatch a failed or cancelled flow run."""
    click.echo(
        "  `forktex cloud deployment retry` is not surfaced by the cloud API yet — "
        "there is no /flows/{id}/retry route. Re-dispatch via `forktex cloud apply` "
        "or `forktex cloud deploy` against the original project/environment.",
        err=True,
    )
    raise click.exceptions.Exit(2)
