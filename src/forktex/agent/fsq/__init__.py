"""Legacy ``forktex.agent.fsq`` compatibility layer.

The canonical command surface is ``forktex.agent.fsd`` / ``forktex fsd``.
This module preserves ``forktex fsq`` as a backward-compatible alias.
"""

from __future__ import annotations

import asyncclick as click

from forktex.agent.fsd.check import check
from forktex.agent.fsd.report import report
from forktex.core.paths import resolve_path


@click.group()
@click.option("--project-dir", default=None, help="Project root directory (default: cwd)")
@click.pass_context
async def fsq(ctx, project_dir):
    """Legacy alias for the FSD verification and compliance commands."""
    ctx.ensure_object(dict)
    ctx.obj["project_root"] = resolve_path(project_dir)


fsq.add_command(check)
fsq.add_command(report)
