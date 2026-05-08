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

"""forktex cloud inspect — detailed view of a single resource."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.group()
async def inspect():
    """Detailed inspection of a single resource.

    \b
    Examples:
        forktex cloud inspect org
        forktex cloud inspect project
        forktex cloud inspect project <id>
        forktex cloud inspect env
        forktex cloud inspect env <id>
        forktex cloud inspect server
        forktex cloud inspect server <id>
    """


@inspect.command(name="org")
@click.pass_context
@translate_cloud_errors
async def inspect_org(ctx):
    """Inspect the active organisation: quota, providers, members."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        orgs = client.list_orgs()
        providers = client.list_providers()
        usage = client.get_usage()
        projects = client.list_projects()

    if not orgs:
        raise click.ClickException("No organisations found.")

    org = orgs[0]
    o_id = getattr(org, "id", "?")
    o_slug = getattr(org, "slug", str(o_id)[:8])

    click.echo()
    click.echo(click.style(f"  Org: {o_slug}  [{o_id}]", bold=True, fg="cyan"))
    click.echo(f"  Projects: {len(projects)}")
    click.echo()

    if providers:
        click.echo(click.style("  Provider credentials:", bold=True))
        for p in providers:
            status = (
                click.style("✓ active", fg="green")
                if p.is_active
                else click.style("revoked", fg="red")
            )
            env_tag = f"  [{p.environment}]" if p.environment else ""
            click.echo(
                f"    {p.provider}/{p.kind}{env_tag}  {status}  label={p.label!r}"
            )
    else:
        click.echo("  Provider credentials: (none)")

    click.echo()
    if usage:
        click.echo(click.style("  Usage:", bold=True))
        for field in ("deployments", "environments", "projects", "storage_bytes"):
            val = getattr(usage, field, None)
            if val is not None:
                click.echo(f"    {field}: {val}")


@inspect.command(name="project")
@click.argument("project_id", required=False, default=None)
@click.pass_context
@translate_cloud_errors
async def inspect_project(ctx, project_id):
    """Inspect a project and its environments. Uses active project if ID not given."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    pid = project_id or cloud_ctx.current_project
    if not pid:
        raise click.ClickException(
            "No project ID given and no active project set. Run: forktex cloud use project <name>"
        )

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        project = client.get_project(pid)
        envs = client.list_project_environments(pid)

    p_name = getattr(project, "name", pid[:8])
    p_id = getattr(project, "id", pid)
    p_created = str(
        getattr(project, "createdAt", None) or getattr(project, "created_at", "")
    )[:16]

    click.echo()
    click.echo(click.style(f"  Project: {p_name}  [{p_id}]", bold=True, fg="cyan"))
    click.echo(f"  Created: {p_created}")
    click.echo(f"  Environments: {len(envs)}")
    click.echo()

    for env in envs:
        e_id = getattr(env, "id", None) or getattr(env, "environmentId", "?")
        e_name = getattr(env, "name", str(e_id)[:8])
        e_status = getattr(env, "status", None) or getattr(
            env, "environmentStatus", "?"
        )
        e_region = getattr(env, "region", None) or getattr(env, "providerRegion", "?")
        status_color = "green" if str(e_status) == "active" else "yellow"
        click.echo(
            f"  ├── {click.style(e_name, bold=True)}  [{str(e_id)[:8]}]"
            f"  status={click.style(str(e_status), fg=status_color)}"
            f"  region={e_region}"
        )

        try:
            with ForktexCloudClient.from_context(cloud_ctx) as client:
                deployments = client.list_deployments(str(p_id), str(e_id))
            if deployments:
                last = deployments[-1]
                d_status = (
                    last.get("status", "?")
                    if isinstance(last, dict)
                    else getattr(last, "status", "?")
                )
                d_at = (
                    last.get("created_at", "")
                    if isinstance(last, dict)
                    else getattr(last, "createdAt", "")
                )
                d_str = str(d_at)[:16].replace("T", " ") if d_at else ""
                d_color = (
                    "green"
                    if d_status == "success"
                    else ("red" if d_status == "failed" else "yellow")
                )
                click.echo(
                    f"  │   last deploy: {click.style(d_status, fg=d_color)}  {d_str}"
                    f"  ({len(deployments)} total)"
                )
        except Exception:
            pass
    click.echo()


@inspect.command(name="env")
@click.argument("environment_id", required=False, default=None)
@click.pass_context
@translate_cloud_errors
async def inspect_env(ctx, environment_id):
    """Inspect an environment: manifest, services, deployments. Uses active env if ID not given."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    pid = cloud_ctx.current_project
    eid = environment_id or cloud_ctx.current_environment

    if not pid:
        raise click.ClickException(
            "No active project. Run: forktex cloud use project <name>"
        )
    if not eid:
        raise click.ClickException(
            "No environment ID given and no active env set. Run: forktex cloud use env <name>"
        )

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        env = client.get_environment(pid, eid)
        deployments = client.list_deployments(pid, eid)
        services = client.list_services(pid, eid)

    e_name = getattr(env, "name", eid[:8])
    e_id = getattr(env, "id", eid)
    e_status = getattr(env, "status", None) or getattr(env, "environmentStatus", "?")
    e_region = getattr(env, "region", None) or getattr(env, "providerRegion", "?")

    click.echo()
    click.echo(click.style(f"  Environment: {e_name}  [{e_id}]", bold=True, fg="cyan"))
    click.echo(f"  Status: {e_status}  Region: {e_region}")
    click.echo(f"  Deployments: {len(deployments)}")
    click.echo()

    if services:
        click.echo(click.style("  Services:", bold=True))
        for svc in services:
            svc_name = getattr(svc, "name", None) or getattr(svc, "serviceName", "?")
            svc_state = getattr(svc, "state", None) or getattr(svc, "status", "?")
            svc_image = getattr(svc, "image", "") or ""
            svc_color = "green" if svc_state == "running" else "red"
            click.echo(
                f"    {click.style(svc_name, bold=True):30s}  {click.style(svc_state, fg=svc_color):10s}"
                + (f"  {svc_image}" if svc_image else "")
            )

    click.echo()
    if deployments:
        click.echo(click.style("  Recent deployments:", bold=True))
        for d in reversed(deployments[-5:]):
            d_id = d.get("id", "?") if isinstance(d, dict) else getattr(d, "id", "?")
            d_status = (
                d.get("status", "?")
                if isinstance(d, dict)
                else getattr(d, "status", "?")
            )
            d_at = (
                d.get("created_at", "")
                if isinstance(d, dict)
                else getattr(d, "createdAt", "")
            )
            d_str = str(d_at)[:16].replace("T", " ") if d_at else ""
            d_color = (
                "green"
                if d_status == "success"
                else ("red" if d_status == "failed" else "yellow")
            )
            click.echo(
                f"    [{str(d_id)[:8]}]  {click.style(d_status, fg=d_color):12s}  {d_str}"
            )
    click.echo()


@inspect.command(name="server")
@click.argument("server_id", required=False, default=None)
@click.pass_context
@translate_cloud_errors
async def inspect_server(ctx, server_id):
    """Inspect a server: containers, health probes. Uses active server if ID not given."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    sid = server_id or cloud_ctx.current_server
    if not sid:
        raise click.ClickException(
            "No server ID given and no active server set. Run: forktex cloud use server <id>"
        )

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        server = client.get_server(sid)
        status = client.server_status(sid)

    s_name = getattr(server, "name", sid[:8])
    s_ip = getattr(server, "ip", None) or getattr(server, "ipv4", "?")
    s_id = getattr(server, "id", sid)

    click.echo()
    click.echo(click.style(f"  Server: {s_name}  [{s_id}]", bold=True, fg="cyan"))
    click.echo(f"  IP: {s_ip}")
    click.echo()

    containers = status.get("containers", []) if isinstance(status, dict) else []
    if containers:
        click.echo(click.style("  Containers:", bold=True))
        for c in containers:
            c_name = c.get("name", "?")
            c_state = c.get("state", "?")
            c_status = c.get("status", "")
            c_image = c.get("image", "")
            c_color = "green" if c_state == "running" else "red"
            click.echo(
                f"    {click.style(c_name, bold=True):35s}  {click.style(c_state, fg=c_color):10s}"
                + (f"  {c_status}" if c_status and c_status != c_state else "")
                + (f"\n    {'':35s}  image={c_image}" if c_image else "")
            )

    health = status.get("health", {}) if isinstance(status, dict) else {}
    if health:
        click.echo()
        click.echo(click.style("  Health probes:", bold=True))
        for probe, code in health.items():
            c = "green" if str(code).startswith("2") else "red"
            click.echo(f"    {probe:30s}  {click.style(str(code), fg=c)}")
    click.echo()
