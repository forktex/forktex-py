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

"""``forktex serve`` — root-level FastAPI server backed by the live graph."""

from __future__ import annotations

import asyncclick as click

from forktex.runtime.decorators import long_running, needs_project


@click.command("serve")
@click.option("--port", "-p", default=4444, show_default=True, type=int)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
@click.option(
    "--scope",
    type=click.Choice(["project", "os", "all"], case_sensitive=False),
    default="all",
    show_default=True,
)
@long_running(label="serve")
@needs_project
async def serve_cmd(
    port: int,
    host: str,
    project: str | None,
    scope: str,
    project_root=None,
) -> None:
    """Serve a live, browsable view of your project as a web dashboard.

    Spins up a local HTTP server (FastAPI) at the chosen port. Opens the
    project graph, structure spec, and live instance list as JSON
    endpoints, plus an interactive C4 architecture page at ``/c4``.
    Requires the ``forktex[web]`` extra. Press Ctrl+C to stop.
    """
    try:
        from forktex.agent.graph.serve import run_server
    except ModuleNotFoundError as exc:
        raise click.ClickException(
            "`forktex serve` needs the optional 'web' extra: "
            f"pip install 'forktex[web]' ({exc.name} missing)"
        ) from exc

    await run_server(
        host=host, port=port, project_root=project_root, scope=scope.lower()
    )


__all__ = ["serve_cmd"]
