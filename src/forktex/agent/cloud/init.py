"""forktex cloud init — scaffold a new forktex.json manifest (local)."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.option(
    "--kind",
    type=click.Choice(
        ["ProjectDeployment", "StaticSite", "SingleContainer", "NativeBuild"],
        case_sensitive=True,
    ),
    default="ProjectDeployment",
    help="Manifest kind",
)
@click.option("--name", default=None, help="Project name (default: directory name)")
@click.option("--force", is_flag=True, help="Overwrite existing forktex.json")
@click.pass_context
async def init(ctx, kind, name, force):
    """Scaffold a new forktex.json manifest."""
    from forktex_cloud.scaffold.templates import scaffold_manifest

    project_root = ctx.obj["project_root"]
    try:
        path = scaffold_manifest(project_root, kind=kind, name=name, force=force)
    except FileExistsError as e:
        raise click.ClickException(str(e))
    except ValueError as e:
        raise click.ClickException(str(e))

    project_name = name or project_root.name
    click.echo(f"Created {path}")
    click.echo(f"  kind: {kind}")
    click.echo(f"  name: {project_name}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Edit {path.name} to configure your deployment")
    click.echo("  2. forktex cloud validate")
    click.echo("  3. forktex cloud up --env local")
