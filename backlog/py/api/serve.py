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

"""``forktex serve`` — run the generic forktex tool API (HTTP + MCP).

One app, domains at root paths (``/knowledge``, ``/arch``, …), MCP at ``/mcp``.
Needs the optional ``[mcp]`` extra (FastAPI + uvicorn + fastapi_mcp).
"""

from __future__ import annotations

from pathlib import Path

import asyncclick as click

_MISSING_EXTRA = (
    "`forktex serve` needs the optional 'mcp' extra: "
    "pip install 'forktex-py[mcp]'  ({name} missing)"
)


def build_app(project_root: str | Path | None = None, *, read_only: bool = True):
    """Construct the tool API app (importable for ASGI servers / tests).

    Mounts the human graph viewer (the former standalone ``arch serve``) under
    ``/arch`` on the same app — one server, not one-per-command — kept out of
    the MCP tool set (agents use the structured ``/arch/*`` POST tools).
    """
    from forktex.agent.graph.serve import VIEWER_TAG, build_arch_router
    from forktex.api.app import create_app
    from forktex.api.registry import build_domains

    root = Path(project_root).resolve() if project_root else Path.cwd()
    viewer = build_arch_router(root)
    return create_app(
        build_domains(root, read_only=read_only),
        extra_routers=[("/arch", viewer)],
        mcp_exclude_tags=[VIEWER_TAG],
    )


@click.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=4455, show_default=True, type=int)
@click.option("--project", "-d", default=None, help="Project root (default: cwd).")
@click.option(
    "--write/--read-only",
    default=False,
    show_default=True,
    help="Expose knowledge write tools (recycle/retire/rollup). Default: read-only.",
)
async def serve_cmd(host: str, port: int, project: str | None, write: bool) -> None:
    """Serve the forktex tool API — every tool as HTTP + MCP, one app.

    Domains mount at root paths (``/knowledge``, ``/arch``); the OpenAPI is at
    ``/docs`` and the MCP-over-HTTP endpoint at ``/mcp``. Point an MCP client at
    it with ``claude mcp add --transport http forktex http://HOST:PORT/mcp``.
    """
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise click.ClickException(_MISSING_EXTRA.format(name=exc.name)) from exc

    try:
        app = build_app(project, read_only=not write)
    except ModuleNotFoundError as exc:
        raise click.ClickException(_MISSING_EXTRA.format(name=exc.name)) from exc

    from forktex.agent.ui.console import console

    domains = ", ".join(f"/{d}" for d in app.state.__dict__.get("domains", []) or [])
    console.print(
        f"[green]forktex tool API[/green] → http://{host}:{port}  "
        f"[dim](OpenAPI /docs · MCP /mcp · graph viewer /arch/{(' · ' + domains) if domains else ''})[/dim]"
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()


__all__ = ["serve_cmd", "build_app"]
