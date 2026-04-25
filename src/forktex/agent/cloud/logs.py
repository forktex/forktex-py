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

"""forktex cloud logs — hybrid: local loki or remote SSE."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.argument("server_id", required=False, default=None)
@click.option("--service", default=None, help="Filter by service id (e.g. 'api', 'db')")
@click.option("--lines", type=int, default=50, help="Number of log lines")
@click.option(
    "--since", default=None, help="Lookback window (e.g. 1h, 30m, 7d). Requires Loki."
)
@click.option(
    "--query",
    default=None,
    help='Raw LogQL query (e.g. \'{service="api"} |= "ERROR"\'). Requires Loki.',
)
@click.option("--local", is_flag=True, help="Force local Loki log tailing (dev mode)")
@click.pass_context
async def logs(ctx, server_id, service, lines, since, query, local):
    """View service logs (remote SSE or local Loki).

    When Loki is available on the server (observability.enabled), logs are
    queried via LogQL (structured, searchable, historical). Otherwise falls
    back to `docker logs` over SSH (recent only).

    \b
    Examples:
        forktex cloud logs <server-id>                         # last 50 lines, all services
        forktex cloud logs <server-id> --service api           # filter to 'api' service
        forktex cloud logs <server-id> --since 1h              # last hour (Loki)
        forktex cloud logs <server-id> --query '{service="api"} |= "ERROR"'  # LogQL
    """
    cloud_ctx = ctx.obj["cloud_ctx"]

    if local or not cloud_ctx.is_connected:
        _local_logs(ctx, service=service)
    else:
        if not server_id:
            server_id = cloud_ctx.current_server
        if not server_id:
            raise click.ClickException("Provide a server_id or set a current server.")
        _remote_logs(
            ctx, server_id, service=service, lines=lines, since=since, query=query
        )


def _remote_logs(ctx, server_id, *, service, lines, since, query):
    cloud_ctx = ctx.obj["cloud_ctx"]

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        try:
            for line in client.stream_logs(
                server_id,
                service=service,
                lines=lines,
                since=since,
                query=query,
            ):
                click.echo(line)
        except KeyboardInterrupt:
            click.echo()


def _local_logs(ctx, *, service):
    import time

    from forktex_cloud.bridge.log_formatter import COLORS, assign_colors, format_line
    from forktex_cloud.bridge.loki import build_logql, loki_ready, tail

    base_url = "http://localhost:3100"
    if not loki_ready(base_url):
        click.echo("Loki not reachable at localhost:3100")
        return

    services: list[str] | None = None
    if service:
        services = [s.strip() for s in service.split(",") if s.strip()]

    logql = build_logql(services)
    start_ns = int((time.time() - 600) * 1_000_000_000)

    color_map = assign_colors(services or [])
    max_name_len = max((len(s) for s in (services or [])), default=8)

    try:
        for ts_ns, svc_name, line in tail(base_url, logql, start_ns):
            if svc_name not in color_map:
                color_map[svc_name] = COLORS[len(color_map) % len(COLORS)]
                if len(svc_name) > max_name_len:
                    max_name_len = len(svc_name)
            click.echo(
                format_line(ts_ns, svc_name, line, color_map[svc_name], max_name_len)
            )
    except KeyboardInterrupt:
        click.echo()
