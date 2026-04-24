"""forktex cloud down — tear down (remote or local dev)."""

from __future__ import annotations

import subprocess
import sys

import asyncclick as click


@click.command()
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--keep-dns", is_flag=True, help="Keep DNS records")
@click.option(
    "--env", "environment", default=None, help="Environment (local for local teardown)"
)
@click.pass_context
async def down(ctx, yes, keep_dns, environment):
    """Tear down: destroy server + DNS (remote) or stop containers (local)."""
    if environment == "local":
        project_root = ctx.obj["project_root"]
        compose_file = str(project_root / ".forktex" / "docker-compose.local.yml")

        # Resolve project name from manifest for compose isolation
        project_name = "forktex"
        try:
            from forktex_cloud.manifest.loader import Manifest

            manifest = Manifest.load(project_root / "forktex.json", env="local")
            project_name = manifest.name or "forktex"
        except (FileNotFoundError, ValueError, KeyError):
            click.echo(
                f"Warning: could not load manifest, using project name '{project_name}'",
                err=True,
            )

        result = subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                project_name,
                "-f",
                compose_file,
                "down",
                "-v",
                "--remove-orphans",
            ],
        )
        if result.returncode != 0:
            sys.exit(result.returncode)
        return

    if not yes:
        click.confirm("This will tear down the deployment. Continue?", abort=True)

    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()
    project_root = ctx.obj["project_root"]

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        click.echo(f"Running down pipeline via {cloud_ctx.controller}...")
        result = client.down(
            keep_dns=keep_dns,
            project_dir=project_root,
        )
        click.echo(f"Down pipeline complete: {result.status}")
