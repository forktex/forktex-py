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

"""forktex.agent.fsd - FSD CLI command group."""

from __future__ import annotations

from pathlib import Path

import asyncclick as click

from forktex.agent.fsd.check import check
from forktex.agent.fsd.ecosystem_cmd import ecosystem
from forktex.agent.fsd.makefile_cli import makefile_group
from forktex.agent.fsd.report import report


@click.group()
@click.option(
    "--project-dir",
    "-d",
    default=None,
    help="Project root (default: walk upward from cwd to find forktex.json)",
)
@click.pass_context
async def fsd(ctx, project_dir):
    """Verify your project against the delivery standard (FSD).

    Runs structural + quality checks, scores a maturity level (L0–L4),
    and writes evidence under ``.forktex/fsd/evidence/`` so audits and
    compliance reporting are always one command away. Walks upward from
    the current directory to find the project, or pass ``--project-dir``.
    """
    from forktex.core.paths import find_project_root
    from forktex.runtime.lifecycle import ensure_runtime

    if project_dir is not None:
        start = Path(project_dir).resolve()
    else:
        start = Path.cwd().resolve()
    found = find_project_root(start)
    if found is None:
        # Allow `fsd ecosystem` to override; otherwise hard fail at the
        # subcommand level so users get the canonical message.
        if ctx.invoked_subcommand != "ecosystem":
            raise click.ClickException(
                f"no forktex.json found at or above {start}.\n"
                "Run from a project directory or pass --project-dir /path/to/project."
            )
        ctx.ensure_object(dict)
        ctx.obj["project_root"] = start
        return

    ensure_runtime(needs_project=True, kind="fsd", project_hint=str(found))
    ctx.ensure_object(dict)
    ctx.obj["project_root"] = found


fsd.add_command(check)
fsd.add_command(report)
fsd.add_command(makefile_group)
fsd.add_command(ecosystem)
