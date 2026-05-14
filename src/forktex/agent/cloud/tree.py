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

"""forktex cloud tree — display the full resource hierarchy."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.command()
@click.option("--org", default=None, help="Filter to a specific org slug or ID")
@click.pass_context
@translate_cloud_errors
async def tree(ctx, org):
    """Display the full resource hierarchy: account → org → project → env → server → service.

    \b
    Example:
        forktex cloud tree
        forktex cloud tree --org my-org
    """
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud import Cloud

    with Cloud.from_context(cloud_ctx) as client:
        me = client.me()
        orgs = client.list_orgs()
        projects = client.list_projects()
        servers = client.list_servers()

    user = getattr(me, "user", None)
    email = getattr(user, "email", None) if user else getattr(me, "email", "?") or "?"
    email_verified = getattr(user, "emailVerified", False) if user else False
    verified_str = (
        click.style("✓", fg="green") if email_verified else click.style("✗", fg="red")
    )

    click.echo()
    click.echo(
        f"account: {click.style(email, bold=True)}  (email_verified: {verified_str})"
    )
    click.echo()

    if not orgs:
        click.echo("  (no organisations)")
        return

    for o in orgs:
        o_id = getattr(o, "id", None) or getattr(o, "orgId", "?")
        o_slug = getattr(o, "slug", None) or str(o_id)[:8]
        if org and org not in (o_slug, str(o_id)):
            continue

        click.echo(
            f"└── org: {click.style(o_slug, fg='cyan', bold=True)}  [{_short(o_id)}]"
        )

        # Providers
        try:
            with Cloud.from_context(cloud_ctx) as client:
                providers = client.list_providers()
            if providers:
                pstr = "  ".join(
                    f"{click.style(p.provider, fg='green')} ✓"
                    if p.is_active
                    else p.provider
                    for p in providers
                )
                click.echo(f"    ├── providers: {pstr}")
        except Exception:
            pass

        # Vault key count
        try:
            with Cloud.from_context(cloud_ctx) as client:
                vault_keys = client.vault_list()
            if vault_keys is not None:
                click.echo(f"    ├── vault: {len(vault_keys)} keys (global)")
        except Exception:
            pass

        # Projects
        org_projects = [
            p
            for p in projects
            if str(getattr(p, "orgId", getattr(p, "org_id", None))) == str(o_id)
        ]
        if not org_projects:
            click.echo("    │")
            click.echo("    └── (no projects)")
            click.echo()
            continue

        click.echo("    │")
        for pi, project in enumerate(org_projects):
            p_id = getattr(project, "id", None) or getattr(project, "projectId", "?")
            p_name = getattr(project, "name", str(p_id)[:8])
            is_last_project = pi == len(org_projects) - 1
            p_prefix = "    └──" if is_last_project else "    ├──"
            p_cont = "        " if is_last_project else "    │   "
            click.echo(
                f"{p_prefix} project: {click.style(p_name, bold=True)}  [{_short(p_id)}]"
            )

            # Environments
            try:
                with Cloud.from_context(cloud_ctx) as client:
                    envs = client.list_project_environments(str(p_id))
            except Exception:
                envs = []

            if not envs:
                click.echo(f"{p_cont}└── (no environments)")
                continue

            for ei, env in enumerate(envs):
                e_id = getattr(env, "id", None) or getattr(env, "environmentId", "?")
                e_name = getattr(env, "name", str(e_id)[:8])
                e_status = getattr(env, "status", None) or getattr(
                    env, "environmentStatus", "?"
                )
                is_last_env = ei == len(envs) - 1
                e_prefix = f"{p_cont}└──" if is_last_env else f"{p_cont}├──"
                e_cont = f"{p_cont}    " if is_last_env else f"{p_cont}│   "

                # Find matching server
                env_server = next(
                    (
                        s
                        for s in servers
                        if str(
                            getattr(
                                s, "environmentId", getattr(s, "environment_id", None)
                            )
                        )
                        == str(e_id)
                    ),
                    None,
                )
                server_str = ""
                if env_server:
                    s_id = getattr(env_server, "id", "?")
                    s_ip = getattr(env_server, "ip", None) or getattr(
                        env_server, "ipv4", "?"
                    )
                    s_name = getattr(env_server, "name", str(s_id)[:8])
                    server_str = (
                        f"  server: {click.style(s_name, fg='yellow')}  ip={s_ip}"
                    )

                status_color = "green" if str(e_status) == "active" else "yellow"
                click.echo(
                    f"{e_prefix} env: {click.style(e_name, bold=True)}  [{_short(e_id)}]"
                    f"  status={click.style(str(e_status), fg=status_color)}{server_str}"
                )

                # Deployments (last one)
                try:
                    with Cloud.from_context(cloud_ctx) as client:
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
                            f"{e_cont}├── last deploy: {click.style(d_status, fg=d_color)}  {d_str}"
                        )
                except Exception:
                    pass

                # Services
                if env_server:
                    try:
                        with Cloud.from_context(cloud_ctx) as client:
                            services = client.list_services(str(p_id), str(e_id))
                        for si, svc in enumerate(services):
                            svc_name = getattr(svc, "name", None) or getattr(
                                svc, "serviceName", "?"
                            )
                            svc_state = getattr(svc, "state", None) or getattr(
                                svc, "status", "?"
                            )
                            svc_image = getattr(svc, "image", "")
                            is_last_svc = si == len(services) - 1
                            svc_prefix = (
                                f"{e_cont}└──" if is_last_svc else f"{e_cont}├──"
                            )
                            svc_color = "green" if svc_state == "running" else "red"
                            click.echo(
                                f"{svc_prefix} service: {click.style(svc_name, bold=True)}"
                                f"  {click.style(svc_state, fg=svc_color)}"
                                + (f"  image={svc_image}" if svc_image else "")
                            )
                    except Exception:
                        pass

        click.echo()


def _short(uid) -> str:
    return str(uid)[:8] if uid else "?"
