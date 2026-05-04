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

"""forktex cloud validate — validate manifest (local)."""

from __future__ import annotations

import asyncclick as click


@click.command()
@click.option("--manifest", default=None, help="Manifest path (default: forktex.json)")
@click.option(
    "--env",
    "environment",
    default=None,
    help="Apply forktex.<env>.json overlay before validating (e.g. staging, production)",
)
@click.pass_context
async def validate(ctx, manifest, environment):
    """Validate a forktex.json manifest (optionally overlaid with --env)."""
    from pathlib import Path
    from forktex_cloud.manifest.loader import Manifest, ManifestError

    project_root = ctx.obj["project_root"]
    mpath = Path(manifest) if manifest else project_root / "forktex.json"

    # Manifest.load runs the canonical Pydantic schema validation
    # eagerly in __init__ and raises ManifestError on bad input.
    try:
        Manifest.load(mpath, env=environment)
    except ManifestError as e:
        raise click.ClickException(str(e))

    suffix = f" (env={environment})" if environment else ""
    click.echo(f"Manifest valid: {mpath}{suffix}")
