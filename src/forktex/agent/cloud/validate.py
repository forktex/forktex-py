"""forktex cloud validate — validate manifest (local)."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.option("--manifest", default=None, help="Manifest path (default: forktex.json)")
@click.pass_context
async def validate(ctx, manifest):
    """Validate a forktex.json manifest."""
    from pathlib import Path
    from forktex_cloud.manifest.loader import Manifest, ManifestError
    from forktex_cloud.manifest.validators import validate as do_validate

    project_root = ctx.obj["project_root"]
    mpath = Path(manifest) if manifest else project_root / "forktex.json"

    try:
        m = Manifest.load(mpath)
        do_validate(m)
    except ManifestError as e:
        raise click.ClickException(str(e))

    click.echo(f"Manifest valid: {mpath}")
