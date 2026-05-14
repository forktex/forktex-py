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

"""forktex cloud logs — unified log primitive via API.

Three modes:
  (default)         last flow run events for the most recent deployment
  --run <run_id>    stream SSE events from a specific flow run
  --service <id>    stream live service logs from a server (SSE)
  --deployment <id> show stored DeploymentLog entries for a completed deploy

All modes go through the cloud API. No direct Loki or SSH access.
"""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.command()
@click.option("--run", "run_id", default=None, help="Stream SSE events for a flow run")
@click.option(
    "--service",
    "server_id",
    default=None,
    help="Stream live service logs from a server",
)
@click.option(
    "-s",
    "--svc",
    "service_filter",
    default=None,
    help="Filter to a specific service name (e.g. 'api')",
)
@click.option(
    "--deployment", "deployment_id", default=None, help="Show stored deployment logs"
)
@click.option(
    "--lines",
    type=int,
    default=100,
    help="Lines to tail for service logs (default: 100)",
)
@click.option(
    "--since", default=None, help="Lookback window for service logs (e.g. 1h, 30m)"
)
@click.pass_context
@translate_cloud_errors
async def logs(ctx, run_id, server_id, service_filter, deployment_id, lines, since):
    """Stream logs via the cloud API.

    \b
    Modes:
      forktex cloud logs                          # last deployment's run events
      forktex cloud logs --run <run_id>           # specific flow run SSE stream
      forktex cloud logs --service <server_id>    # live service logs (all services)
      forktex cloud logs --service <id> -s api    # live logs for a specific service
      forktex cloud logs --deployment <dep_id>    # stored deployment log entries
    """
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    # Apply context defaults
    if not server_id and cloud_ctx.current_server:
        server_id = cloud_ctx.current_server

    from forktex_cloud import Cloud

    with Cloud.from_context(cloud_ctx) as client:
        if server_id:
            _stream_service_logs(
                client, server_id, service=service_filter, lines=lines, since=since
            )
        elif deployment_id:
            _show_deployment_logs(client, deployment_id, ctx)
        elif run_id:
            _stream_run_events(client, run_id)
        else:
            _stream_latest_run(client)


def _stream_service_logs(
    client, server_id: str, *, service: str | None, lines: int, since: str | None
) -> None:
    """Stream live service logs from a server via SSE."""
    svc_label = service or "all services"
    click.echo(
        click.style(f"  Streaming logs — server {server_id[:8]}… {svc_label}", dim=True)
    )
    click.echo()
    try:
        for line in client.stream_logs(
            server_id,
            service=service,
            lines=lines,
            since=since,
        ):
            click.echo(line)
    except KeyboardInterrupt:
        click.echo()


def _stream_run_events(client, run_id: str) -> None:
    """Stream SSE events for a flow run with colored step output."""
    click.echo(click.style(f"  Streaming run {run_id[:8]}…", dim=True))
    click.echo()

    _COLORS = {
        "running": ("cyan", "▶"),
        "completed": ("green", "✓"),
        "failed": ("red", "✗"),
        "cancelled": ("yellow", "⊘"),
        "pending": ("white", "·"),
    }

    try:
        for event in client.stream_flow_run(run_id):
            step_name = event.get("stepName") if isinstance(event, dict) else getattr(event, "stepName", None)
            status = (event.get("status") if isinstance(event, dict) else getattr(event, "status", "")) or ""

            if step_name:
                color, icon = _COLORS.get(status, ("white", "?"))
                label = click.style(f"{icon} {step_name}", fg=color)
                click.echo(f"  {label}")
            else:
                if status in ("completed", "failed", "cancelled"):
                    color = (
                        "green"
                        if status == "completed"
                        else "red"
                        if status == "failed"
                        else "yellow"
                    )
                    icon = (
                        "✓"
                        if status == "completed"
                        else "✗"
                        if status == "failed"
                        else "⊘"
                    )
                    click.echo()
                    click.echo(
                        f"  {click.style(icon + ' Run ' + status, fg=color, bold=True)}"
                    )
    except KeyboardInterrupt:
        click.echo()


def _stream_latest_run(client) -> None:
    """Find the most recent flow run and stream its events (or show stored logs if finished)."""
    runs = client.list_flow_runs(limit=1)
    if not runs:
        click.echo("  No flow runs found.")
        return

    run = runs[0]
    # list_flow_runs returns raw dicts — accessor shape may evolve in
    # forktex_core.flow; iterate defensively.
    run_id = str(run.get("runId") or run.get("run_id") or "")
    status = run.get("status") or ""

    click.echo(click.style(f"  Last run: {run_id[:8]}…  status={status}", dim=True))

    if status == "running":
        _stream_run_events(client, run_id)
    else:
        _render_finished_run(run)


def _render_finished_run(run: dict) -> None:
    """Print a summary of a finished flow run (raw dict from list_flow_runs)."""
    _COLORS = {
        "completed": "green",
        "failed": "red",
        "cancelled": "yellow",
    }
    status = run.get("status") or ""
    color = _COLORS.get(status, "white")
    click.echo(f"  {click.style(status.upper(), fg=color, bold=True)}")
    click.echo()
    for step in run.get("steps") or run.get("nodes") or []:
        step_status = step.get("status", "") if isinstance(step, dict) else ""
        step_name = step.get("stepName") or step.get("name") or step_status if isinstance(step, dict) else "?"
        step_color = _COLORS.get(step_status, "white")
        icon = (
            "✓"
            if step_status == "completed"
            else "✗"
            if step_status == "failed"
            else "·"
        )
        click.echo(f"  {click.style(icon, fg=step_color)} {step_name}")

    err = run.get("error")
    if err:
        click.echo()
        click.echo(click.style("  Error:", fg="red", bold=True))
        click.echo(f"  {str(err)[:400]}")


def _show_deployment_logs(client, deployment_id: str, ctx) -> None:
    """Show stored DeploymentLog entries for a deployment."""
    projects = client.list_projects()
    for project in projects:
        envs = client.list_project_environments(str(project.id))
        for env in envs:
            deps = client.list_deployments(str(project.id), str(env.id))
            for dep in deps:
                dep_id = (
                    dep.get("id")
                    if isinstance(dep, dict)
                    else str(getattr(dep, "id", ""))
                )
                if dep_id == deployment_id or dep_id.startswith(deployment_id):
                    entries = client.get_deployment_logs(
                        str(project.id), str(env.id), dep_id
                    )
                    _render_deployment_logs(dep, entries)
                    return
    click.echo(f"  Deployment {deployment_id} not found.")


def _render_deployment_logs(deployment, entries) -> None:
    status = deployment.get("status", "?") if isinstance(deployment, dict) else getattr(deployment, "status", "?")
    details = deployment.get("details", "") if isinstance(deployment, dict) else getattr(deployment, "details", "")

    color = "green" if status == "success" else "red" if status == "failed" else "white"
    click.echo(f"\n  Deployment: {click.style(status.upper(), fg=color, bold=True)}")
    if details:
        click.echo(f"  {str(details)[:300]}")
    click.echo()

    if not entries:
        click.echo("  (no log entries)")
        return

    for entry in entries:
        # DeploymentLogRead is a Pydantic model — use attribute access
        stage = getattr(entry, "stage", "?")
        output = getattr(entry, "output", "") or ""
        error = getattr(entry, "error", "") or ""
        ts = str(getattr(entry, "createdAt", None) or getattr(entry, "created_at", ""))[:19]

        stage_color = "red" if error else "white"
        click.echo(click.style(f"  [{ts}] {stage}", fg=stage_color))
        if error:
            click.echo(click.style(f"    ERROR: {str(error)[:300]}", fg="red"))
        if output and not error:
            for line in str(output).splitlines()[:5]:
                click.echo(f"    {line}")
