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

"""``forktex arch serve`` — FastAPI server backed by the live graph.

Each request rebuilds the graph from disk, so changes are visible
without restarting the server. The HTML page returned at ``/`` is the
exact same template used for the static ``graph.html`` export, with the
payload swapped in from ``/api/graph``.
"""

from __future__ import annotations

from pathlib import Path

from forktex.graph.build import build_graph
from forktex.graph.export.html_writer import render_html
from forktex.graph.export.json_writer import render_json
from forktex.graph.models import Scope
from forktex.graph.scopes import OSScope, ProjectScope


def _build(scope: Scope, project_root: Path):
    if scope == "os":
        return build_graph(OSScope())
    return build_graph(ProjectScope(project_root))


#: Tag for the human-facing viewer routes — excluded from the MCP surface (the
#: agent has the structured POST `/arch/*` tool versions; these are HTML/JSON
#: GETs for a browser), so mounting the viewer on the generic app adds no noise.
VIEWER_TAG = "arch-viewer"


def build_arch_router(project_root: Path, *, default_scope: str = "project"):
    """The graph-viewer routes as a router — the live dashboard + graph JSON.

    Shared by the standalone ``forktex arch serve`` (mounted at ``/``) and the
    generic tool API (mounted under ``/arch`` by ``forktex serve``), so there is
    one viewer, not a per-command server.
    """
    from fastapi import APIRouter, Response
    from fastapi.responses import HTMLResponse, JSONResponse

    router = APIRouter(tags=[VIEWER_TAG])

    def _scope_for(req_scope: str | None) -> Scope:
        s = (req_scope or default_scope or "project").lower()
        if s == "all":
            s = "project"
        return "os" if s == "os" else "project"

    @router.get("/api/graph")
    def api_graph(scope: str | None = None):
        graph_obj = _build(_scope_for(scope), project_root)
        return Response(content=render_json(graph_obj), media_type="application/json")

    @router.get("/api/scopes")
    def api_scopes():
        return JSONResponse(
            {
                "available": ["project", "os"],
                "default": _scope_for(default_scope),
                "project_root": str(project_root),
            }
        )

    @router.get("/api/structure")
    def api_structure(scope: str | None = None):
        from forktex.substrate import spec as _structure

        s = _scope_for(scope)
        return JSONResponse(
            {
                "scope": s,
                "entries": [
                    {
                        "pattern": e.pattern,
                        "kind": e.kind,
                        "purpose": e.purpose,
                        "sensitivity": e.sensitivity,
                        "required": e.required,
                        "writers": list(e.writers),
                    }
                    for e in _structure.spec_for(s)
                ],
            }
        )

    @router.get("/", response_class=HTMLResponse)
    def index(scope: str | None = None):
        graph_obj = _build(_scope_for(scope), project_root)
        return HTMLResponse(render_html(graph_obj, render_json(graph_obj)))

    @router.get("/c4", response_class=HTMLResponse)
    def c4(scope: str | None = None):
        from forktex.graph.export.c4_html_writer import render_c4_html

        graph_obj = _build(_scope_for(scope), project_root)
        return HTMLResponse(render_c4_html(graph_obj))

    @router.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @router.get("/api/instances")
    def api_instances():
        from dataclasses import asdict

        from forktex.runtime import iter_running_instances

        return JSONResponse(
            {
                "instances": [
                    asdict(rec)
                    for rec in iter_running_instances()
                    if rec.status == "running"
                ]
            }
        )

    return router


async def run_server(*, host: str, port: int, project_root: Path, scope: str) -> None:
    """Run the standalone graph viewer (``forktex arch serve``) until interrupted."""

    from fastapi import FastAPI
    import uvicorn

    app = FastAPI(
        title="ForkTex Graph",
        description="Source-of-truth multi-edge graph for ForkTex projects.",
    )
    app.include_router(build_arch_router(project_root, default_scope=scope))

    _print_bind_banner(host=host, port=port, project_root=project_root, scope=scope)

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


def _print_bind_banner(*, host: str, port: int, project_root: Path, scope: str) -> None:
    """Show the user where to point their browser before uvicorn takes over stdout."""
    from forktex.agent.ui.console import console

    base = f"http://{host}:{port}"
    console.print("[green]✓[/green] [bold]ForkTex graph server[/bold]")
    console.print(f"  [cyan]{base}[/cyan]              dashboard")
    console.print(f"  [cyan]{base}/c4[/cyan]            C4 drill-down view")
    console.print(f"  [cyan]{base}/api/graph[/cyan]")
    console.print(f"  [cyan]{base}/api/instances[/cyan]")
    console.print(f"  [cyan]{base}/api/structure[/cyan]")
    console.print(f"  [cyan]{base}/healthz[/cyan]")
    console.print(f"  [dim]project: {project_root}   scope: {scope}[/dim]")
    console.print("  [dim]Press Ctrl+C to stop.[/dim]")


__all__ = ["run_server", "build_arch_router", "VIEWER_TAG"]
