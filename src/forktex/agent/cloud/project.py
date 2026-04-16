"""forktex cloud project — project namespace operations (remote)."""

from __future__ import annotations

import asyncclick as click


@click.group()
@click.pass_context
async def project(ctx):
    """Project management."""
    pass


@project.command("list")
@click.pass_context
async def project_list(ctx):
    """List projects."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        projects = client.list_projects()

    if not projects:
        click.echo("No projects.")
        return
    for p in projects:
        click.echo(f"  {p.id}  {p.name}")


@project.command("create")
@click.option("--name", required=True, help="Project name")
@click.option("--manifest", default=None, help="Manifest path")
@click.option("--id", "project_id", default=None, help="Custom project ID")
@click.pass_context
async def project_create(ctx, name, manifest, project_id):
    """Create a project."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.create_project(name, manifest=manifest, project_id=project_id)
    click.echo(result.model_dump_json(indent=2))


@project.command("show")
@click.option("--id", "project_id", required=True, help="Project ID")
@click.pass_context
async def project_show(ctx, project_id):
    """Show project details."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        proj = client.get_project(project_id)
    click.echo(proj.model_dump_json(indent=2))
