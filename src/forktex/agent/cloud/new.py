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

"""forktex cloud new — create a project from a template with guided onboarding."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.command()
@click.argument("template_slug", required=False, default=None)
@click.option("--name", default=None, help="Project name")
@click.option("--domain", default=None, help="Primary domain for the project")
@click.option(
    "--env", default="production", help="Environment name (default: production)"
)
@click.option(
    "--list", "list_only", is_flag=True, help="List available templates and exit"
)
@click.pass_context
@translate_cloud_errors
async def new(ctx, template_slug, name, domain, env, list_only):
    """Create a new project from a template by slug.

    \b
    Examples:
        forktex cloud new hello-world --name my-site
        forktex cloud new fullstack --name my-app

    Note: ``--list`` and template discovery aren't surfaced by the cloud API
    yet (no ``list_templates`` / ``get_template`` routes). Pass the slug of a
    known template (hello-world, fullstack, static-react, single-container,
    native-go, website, ...) directly.
    """
    if list_only:
        click.echo(
            "  Template listing isn't surfaced by the cloud API yet. Available "
            "slugs are documented in templates/ in the cloud repo; common ones:\n"
            "    hello-world  fullstack  static-react  single-container  native-go",
            err=True,
        )
        raise click.exceptions.Exit(2)

    if not template_slug:
        raise click.ClickException(
            "Pass a template slug (e.g. `forktex cloud new hello-world --name my-site`)."
        )

    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud import Cloud

    project_name = name or template_slug
    overrides: dict | None = None
    if domain:
        overrides = {
            "cloud": {
                "infrastructure": {
                    "servers": [
                        {"id": "primary", "gateway": {"domain": domain}}
                    ]
                }
            }
        }

    with Cloud.from_context(cloud_ctx) as client:
        resp = client.create_from_template(
            slug=template_slug,
            project_name=project_name,
            overrides=overrides,
        )

    project_id = getattr(resp, "projectId", None) or getattr(resp, "project_id", "")
    environment_id = getattr(resp, "environmentId", None) or getattr(
        resp, "environment_id", ""
    )
    bundle_url = getattr(resp, "bundleUrl", None) or getattr(resp, "bundle_url", None)

    click.echo(click.style("  ✓  Project created", fg="green"))
    click.echo(f"     project_id={project_id}")
    click.echo(f"     environment_id={environment_id}")
    if bundle_url:
        click.echo()
        click.echo(click.style("  Starter code:", bold=True))
        click.echo(f"  {cloud_ctx.controller}{bundle_url}")
    click.echo()
    click.echo(click.style("  Ready to deploy:", bold=True))
    click.echo(f"  {click.style('forktex cloud up', fg='cyan', bold=True)}")
    return  # pragma: no cover — old guided-onboarding path below retained for reference

    with Cloud.from_context(cloud_ctx) as client:
        templates = client.list_templates()  # noqa: F841 — gated until route exists

        if list_only or not template_slug:
            _print_template_list(templates)
            if not template_slug:
                click.echo()
                slug = await click.prompt("  Template slug", default="hello-world")
                template_slug = slug

        # Find the chosen template
        tmpl = next((t for t in templates if t.slug == template_slug), None)
        if tmpl is None:
            # Try fetching directly
            try:
                tmpl = client.get_template(template_slug)
            except Exception:
                raise click.ClickException(
                    f"Template not found: {template_slug!r}. Run with --list to see available templates."
                )

        _print_template_detail(tmpl)

        # Prompt for project name if not given
        if not name:
            name = await click.prompt("  Project name", default=template_slug)

        # Show deploy steps
        steps = (
            getattr(tmpl, "deploySteps", None)
            or getattr(tmpl, "deploy_steps", [])
            or []
        )
        if steps:
            click.echo(click.style(f"\n  Onboarding steps for {tmpl.name}:", bold=True))
            for step in steps:
                order = getattr(step, "order", "?")
                title = getattr(step, "title", "")
                desc = getattr(step, "description", "")
                cmd = getattr(step, "command", None)
                click.echo(f"\n  {order}. {click.style(title, bold=True)}")
                click.echo(f"     {desc}")
                if cmd:
                    click.echo(f"     {click.style('$ ' + cmd, fg='cyan', dim=True)}")

        # Handle required secrets
        required = (
            getattr(tmpl, "requiredSecrets", None)
            or getattr(tmpl, "required_secrets", [])
            or []
        )
        if required:
            click.echo(
                click.style(f"\n  Required secrets ({len(required)}):", bold=True)
            )
            for secret in required:
                click.echo(f"  • {secret}")
            click.echo()
            if await click.confirm("  Set these secrets now?", default=True):
                for secret in required:
                    import secrets as _secrets

                    default_val = (
                        _secrets.token_hex(24) if "password" in secret.lower() else ""
                    )
                    val = await click.prompt(
                        f"  {secret}",
                        default=default_val,
                        hide_input="password" in secret.lower(),
                    )
                    if val:
                        client.vault_set(secret, val)
                        click.echo(f"    ✓  {secret} stored")

        # Create the project from template
        click.echo(
            f"\n  Creating project {click.style(name, bold=True)} from template {click.style(template_slug, fg='cyan')}..."
        )

        overrides: dict = {}
        if domain:
            overrides = {
                "cloud": {
                    "infrastructure": {
                        "servers": [
                            {"id": "primary", "gateway": {"domain": domain}}
                        ]
                    }
                }
            }

        resp = client.create_from_template(
            slug=template_slug,
            project_name=name,
            overrides=overrides or None,
        )

        project_id = getattr(resp, "projectId", None) or getattr(resp, "project_id", "")
        environment_id = getattr(resp, "environmentId", None) or getattr(
            resp, "environment_id", ""
        )
        bundle_url = getattr(resp, "bundleUrl", None) or getattr(
            resp, "bundle_url", None
        )

        click.echo(click.style("  ✓  Project created", fg="green"))
        click.echo(f"     project_id={project_id}")
        click.echo(f"     environment_id={environment_id}")

        if bundle_url:
            click.echo(click.style("\n  Starter code available:", bold=True))
            click.echo(f"  {cloud_ctx.controller}{bundle_url}")
            click.echo(f"  Download: curl -O '{cloud_ctx.controller}{bundle_url}'")

        click.echo(click.style("\n  Ready to deploy:", bold=True))
        click.echo(f"  {click.style('forktex cloud up', fg='cyan', bold=True)}")
        click.echo()


def _print_template_list(templates) -> None:
    click.echo(click.style("\n  Available templates:", bold=True))
    click.echo()
    for t in templates:
        slug = t.slug
        name = t.name
        flavour = (
            getattr(t, "recommendedFlavour", None)
            or getattr(t, "recommended_flavour", "?")
            or "?"
        )
        cost = getattr(t, "estimatedMonthlyCostUsd", None) or getattr(
            t, "estimated_monthly_cost_usd", None
        )
        bundle = (
            "📦 "
            if (
                getattr(t, "hasCodeBundle", False)
                or getattr(t, "has_code_bundle", False)
            )
            else "   "
        )
        cost_str = f"~${cost:.2f}/mo" if cost else ""
        click.echo(
            f"  {bundle}{click.style(slug, fg='cyan', bold=True):30}  {name:30}  {flavour:12}  {cost_str}"
        )
    click.echo()


def _print_template_detail(tmpl) -> None:
    name = getattr(tmpl, "name", "")
    desc = getattr(tmpl, "description", "")
    flavour = getattr(tmpl, "recommendedFlavour", None) or getattr(
        tmpl, "recommended_flavour", ""
    )
    cost = getattr(tmpl, "estimatedMonthlyCostUsd", None) or getattr(
        tmpl, "estimated_monthly_cost_usd", None
    )
    tags = getattr(tmpl, "tags", []) or []

    click.echo()
    click.echo(click.style(f"  {name}", bold=True, fg="cyan"))
    click.echo(f"  {desc}")
    details = []
    if flavour:
        details.append(f"flavour: {flavour}")
    if cost:
        details.append(f"~${cost:.2f}/mo")
    if tags:
        details.append(f"tags: {', '.join(tags)}")
    if details:
        click.echo(f"  {' · '.join(details)}")
