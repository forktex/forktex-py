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

"""``forktex graph serve`` — FastAPI server backed by the live graph.

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


async def run_server(*, host: str, port: int, project_root: Path, scope: str) -> None:
    """Run the FastAPI server until interrupted."""

    from fastapi import FastAPI, Response
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn

    app = FastAPI(
        title="ForkTex Graph",
        description="Source-of-truth multi-edge graph for ForkTex projects.",
    )

    def _scope_for(req_scope: str | None) -> Scope:
        s = (req_scope or scope or "project").lower()
        if s == "all":
            s = "project"
        return "os" if s == "os" else "project"

    @app.get("/api/graph")
    def api_graph(scope: str | None = None) -> Response:
        graph_obj = _build(_scope_for(scope), project_root)
        body = render_json(graph_obj)
        return Response(content=body, media_type="application/json")

    @app.get("/api/scopes")
    def api_scopes() -> JSONResponse:
        return JSONResponse(
            {
                "available": ["project", "os"],
                "default": _scope_for(scope),
                "project_root": str(project_root),
            }
        )

    @app.get("/api/structure")
    def api_structure(scope: str | None = None) -> JSONResponse:
        from forktex.graph import structure as _structure

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

    @app.get("/", response_class=HTMLResponse)
    def index(scope: str | None = None) -> HTMLResponse:
        graph_obj = _build(_scope_for(scope), project_root)
        body = render_json(graph_obj)
        # The HTML template embeds the JSON; live mode reuses it verbatim.
        # Defuse any "</" against premature script-tag closing.
        return HTMLResponse(render_html(graph_obj, body))

    @app.get("/c4", response_class=HTMLResponse)
    def c4(scope: str | None = None) -> HTMLResponse:
        from forktex.graph.export.c4_html_writer import render_c4_html

        graph_obj = _build(_scope_for(scope), project_root)
        return HTMLResponse(render_c4_html(graph_obj))

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/instances")
    def api_instances() -> JSONResponse:
        from forktex.runtime import iter_running_instances
        from dataclasses import asdict

        return JSONResponse(
            {
                "instances": [
                    asdict(rec)
                    for rec in iter_running_instances()
                    if rec.status == "running"
                ]
            }
        )

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


__all__ = ["run_server"]
