"""forktex.agent.fsd - FSD CLI command group."""

from __future__ import annotations

import asyncclick as click

from forktex.agent.fsd.check import check
from forktex.agent.fsd.makefile_cli import makefile_group
from forktex.agent.fsd.report import report
from forktex.core.paths import resolve_path


@click.group()
@click.option(
    "--project-dir", default=None, help="Project root directory (default: cwd)"
)
@click.pass_context
async def fsd(ctx, project_dir):
    """FSD - ForkTex Standard for Delivery verification and compliance."""

    ctx.ensure_object(dict)
    ctx.obj["project_root"] = resolve_path(project_dir)


fsd.add_command(check)
fsd.add_command(report)
fsd.add_command(makefile_group)
