"""forktex arch — Auto-discover and visualize project architecture.

Works with any project that has a forktex.json manifest.
Outputs: JSON + HTML + Structurizr DSL.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import asyncclick as click
from jinja2 import Environment, FileSystemLoader

from forktex.agent.fsd.arch import Workspace, to_structurizr_dsl
from forktex.agent.fsd.arch_discover import discover_project, discover_multi
from forktex.core.paths import (
    get_architecture_dir,
    get_fsd_evidence_dir,
    find_project_root,
    has_manifest,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _render_html(workspace: Workspace) -> str:
    total_containers = sum(len(s.containers) for s in workspace.systems)
    total_ports = len(workspace.all_ports)
    total_packages = sum(len(s.packages) for s in workspace.systems)
    total_lines = sum(
        comp.line_count
        for s in workspace.systems
        for c in s.containers
        for comp in c.components
    )
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("arch.html")
    nav_json = json.dumps(workspace.to_navigation())
    edges_json = json.dumps(
        [
            {"source": r.source_id, "target": r.target_id, "label": r.description}
            for r in workspace.relationships
        ]
    )
    return template.render(
        workspace=workspace,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        total_containers=total_containers,
        total_ports=total_ports,
        total_packages=total_packages,
        total_lines=total_lines,
        all_ports=workspace.all_ports,
        nav_json=nav_json,
        edges_json=edges_json,
    )


def _write_outputs(workspace: Workspace, out: Path) -> tuple[Path, Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    json_path = out / f"arch-{ts}.json"
    json_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **workspace.to_dict(),
        "navigation": workspace.to_navigation(),
    }
    json_path.write_text(json.dumps(json_data, indent=2))

    dsl_path = out / f"workspace-{ts}.dsl"
    dsl_path.write_text(to_structurizr_dsl(workspace))

    html_path = out / f"arch-{ts}.html"
    html_path.write_text(_render_html(workspace))

    return json_path, dsl_path, html_path


def _print_system(sys):
    click.echo(f"  {sys.name} (FSD {sys.fsd_level})")
    for c in sys.containers:
        port_str = f":{c.primary_port.host}" if c.primary_port else ""
        click.echo(
            f"    {c.id:<16} {c.service_type.value:<14} {c.tech_summary:<30} {port_str}"
        )
        if c.components:
            click.echo(
                f"      components: {', '.join(comp.name for comp in c.components)}"
            )


# ── Commands ─────────────────────────────────────────────────────────────────


@click.group("arch")
@click.pass_context
async def arch(ctx):
    """Architecture discovery and visualization (C4 model).

    Works with any project that has a forktex.json manifest.
    """
    ctx.ensure_object(dict)


@arch.command("discover")
@click.option(
    "--project-dir", default=".", help="Project root directory (default: cwd)"
)
@click.option(
    "--output-dir",
    default=None,
    help="Output directory (default: .forktex/fsd/evidence/)",
)
async def discover_cmd(project_dir, output_dir):
    """Discover architecture of a project.

    Reads forktex.json, lockfiles, Makefiles, and docker-compose to build
    a C4 Container model. Outputs JSON + HTML + Structurizr DSL.
    """
    root = Path(project_dir).resolve()
    if not has_manifest(root):
        raise click.ClickException(f"No forktex.json found in {root}")

    sys = discover_project(root)
    workspace = Workspace(
        name=sys.name,
        description=sys.description,
        systems=[sys],
    )

    out = Path(output_dir) if output_dir else get_fsd_evidence_dir(root)
    json_path, dsl_path, html_path = _write_outputs(workspace, out)

    click.echo(f"Architecture: {sys.name} (FSD {sys.fsd_level})")
    click.echo(f"{'=' * 50}")
    _print_system(sys)
    click.echo()
    click.echo(f"JSON:          {json_path}")
    click.echo(f"Structurizr:   {dsl_path}")
    click.echo(f"HTML:          {html_path}")


@arch.command("multi")
@click.option(
    "--base-dir",
    default=None,
    help="Parent directory containing projects (default: parent of cwd)",
)
@click.argument("projects", nargs=-1)
@click.option("--output-dir", default=None, help="Output directory")
async def multi_cmd(base_dir, projects, output_dir):
    """Discover architecture across multiple projects.

    Pass project directory names as arguments, or omit to auto-detect all
    projects with forktex.json in the base directory.

    Example: forktex arch multi cloud network intelligence
    """
    if base_dir:
        root = Path(base_dir).resolve()
    else:
        project_root = find_project_root()
        root = project_root.parent if project_root else Path.cwd().resolve()

    project_list = list(projects) if projects else None
    workspace = discover_multi(root, project_list)

    if not workspace.systems:
        raise click.ClickException(f"No projects with forktex.json found in {root}")

    total_containers = sum(len(s.containers) for s in workspace.systems)
    total_ports = len(workspace.all_ports)

    out = Path(output_dir) if output_dir else get_architecture_dir(root)
    json_path, dsl_path, html_path = _write_outputs(workspace, out)

    click.echo(f"Architecture: {workspace.name}")
    click.echo(f"{'=' * 50}")
    click.echo(
        f"Projects: {len(workspace.systems)} | Containers: {total_containers} | Ports: {total_ports}"
    )
    click.echo()

    for sys in workspace.systems:
        _print_system(sys)
        click.echo()

    # Port table
    if workspace.all_ports:
        click.echo("Port Allocation:")
        click.echo(f"  {'Project':<22} {'Service':<12} {'Host':<8} {'Type'}")
        click.echo(f"  {'-' * 52}")
        for p in workspace.all_ports:
            click.echo(
                f"  {p['system']:<22} {p['service']:<12} :{p['host_port']:<6} {p['type']}"
            )
        click.echo()

    click.echo(f"JSON:          {json_path}")
    click.echo(f"Structurizr:   {dsl_path}")
    click.echo(f"HTML:          {html_path}")


@arch.command("report")
@click.option("--base-dir", default=None, help="Parent directory containing projects")
@click.argument("projects", nargs=-1)
@click.option("--output-dir", "-o", default=".", help="Output directory for reports")
@click.option(
    "--pdf", is_flag=True, help="Also generate PDF (requires forktex-documents[pdf])"
)
@click.option("--system", "-s", default=None, help="Report for a single system only")
async def report_cmd(base_dir, projects, output_dir, pdf, system):
    """Generate modular architecture reports (HTML + optional PDF).

    Creates print-ready reports from the architecture data.

    Example:
        forktex arch report --pdf -o reports/
        forktex arch report -s forktex-cloud --pdf
    """
    if base_dir:
        root = Path(base_dir).resolve()
    else:
        project_root = find_project_root()
        root = project_root.parent if project_root else Path.cwd().resolve()

    workspace = discover_multi(root, list(projects) if projects else None)
    if not workspace.systems:
        raise click.ClickException(f"No projects found in {root}")

    total_containers = sum(len(s.containers) for s in workspace.systems)
    total_packages = sum(len(s.packages) for s in workspace.systems)
    total_lines = sum(
        comp.line_count
        for s in workspace.systems
        for c in s.containers
        for comp in c.components
    )

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    files = []

    if system:
        sys_obj = workspace.system_by_id(system)
        if not sys_obj:
            raise click.ClickException(f"System '{system}' not found")
        html = env.get_template("reports/system_report.html").render(
            sys=sys_obj, generated_at=ts
        )
        p = out / f"{system}-report.html"
        p.write_text(html)
        files.append(p)
    else:
        html = env.get_template("reports/ecosystem_report.html").render(
            workspace=workspace,
            generated_at=ts,
            total_containers=total_containers,
            total_ports=len(workspace.all_ports),
            total_packages=total_packages,
            total_lines=total_lines,
            all_ports=workspace.all_ports,
        )
        p = out / "ecosystem-report.html"
        p.write_text(html)
        files.append(p)

    for f in files:
        click.echo(f"  HTML: {f}")

    if pdf:
        try:
            from forktex_documents import render_pdf

            for f in files:
                pdf_bytes = render_pdf(f.read_text(), base_url=str(out))
                pdf_p = Path(str(f).replace(".html", ".pdf"))
                pdf_p.write_bytes(pdf_bytes)
                click.echo(f"  PDF:  {pdf_p}")
        except ImportError:
            click.echo("  PDF requires: pip install forktex-documents[pdf]")


@arch.command("serve")
@click.option("--base-dir", default=None, help="Parent directory")
@click.option("--port", "-p", default=4444, help="Port")
@click.option("--host", default="127.0.0.1", help="Host")
@click.option(
    "--static-dir", default=None, help="Serve React build from this directory"
)
async def serve_cmd(base_dir, port, host, static_dir):
    """Start a live architecture web server.

    Serves architecture as a typed JSON API (with OpenAPI spec for RTK
    codegen) + interactive HTML dashboard. Re-discovers on every request.

    For React integration:
        1. forktex arch serve --port 4444
        2. curl http://localhost:4444/openapi.json > openapi.json
        3. npx @rtk-query/codegen-openapi codegen.config.js
        4. forktex arch serve --static-dir client/build

    Requires: pip install forktex[web]

    Example: forktex arch serve --port 4444
    """
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import HTMLResponse, JSONResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel, Field
        import uvicorn
    except ImportError:
        raise click.ClickException(
            "Live server requires FastAPI + Uvicorn.\n"
            "Install with: pip install forktex[web]"
        )

    if base_dir:
        root = Path(base_dir).resolve()
    else:
        cwd = Path.cwd()
        root = cwd.parent if (cwd / "forktex.json").exists() else cwd

    # ── Pydantic response models (drive OpenAPI spec → RTK codegen) ──

    class TechInfo(BaseModel):
        name: str
        version: str | None = None
        category: str = ""

    class PortInfo(BaseModel):
        host: int
        container: int

    class ComponentInfo(BaseModel):
        id: str
        name: str
        description: str
        technology: str = ""
        files: list[str] = Field(default_factory=list)
        line_count: int = 0

    class ContainerInfo(BaseModel):
        id: str
        name: str
        description: str
        service_type: str
        technology: list[TechInfo] = Field(default_factory=list)
        ports: list[PortInfo] = Field(default_factory=list)
        image: str | None = None
        health_path: str | None = None
        components: list[ComponentInfo] = Field(default_factory=list)

    class GitInfoModel(BaseModel):
        branch: str = ""
        last_commit: str = ""
        message: str = ""
        date: str = ""
        dirty: bool = False
        remote: str = ""

    class PackageInfoModel(BaseModel):
        name: str
        path: str
        version: str = ""
        language: str = "python"
        publishable: bool = False
        description: str = ""

    class EdgeInfo(BaseModel):
        source: str
        target: str
        description: str

    class SystemInfo(BaseModel):
        id: str
        name: str
        description: str
        fsd_level: str = "L0"
        provider: str | None = None
        region: str | None = None
        deploy_strategy: str | None = None
        domains: list[str] = Field(default_factory=list)
        git: GitInfoModel | None = None
        packages: list[PackageInfoModel] = Field(default_factory=list)
        containers: list[ContainerInfo] = Field(default_factory=list)

    class NavigationNode(BaseModel):
        id: str
        name: str
        type: str
        level: int
        data: dict = Field(default_factory=dict)
        children: list["NavigationNode"] = Field(default_factory=list)

    class ArchitectureResponse(BaseModel):
        generated_at: str
        name: str
        description: str
        systems: list[SystemInfo]
        relationships: list[EdgeInfo] = Field(default_factory=list)
        navigation: NavigationNode

    class PortAllocation(BaseModel):
        system: str
        service: str
        host_port: int
        container_port: int
        type: str

    # ── FastAPI app ──

    web_app = FastAPI(
        title="FORKTEX Architecture",
        version="0.1.0",
        description="Live architecture API — auto-discovered from filesystem, git, and forktex.json",
        openapi_url="/openapi.json",
        docs_url="/docs",
    )

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @web_app.get(
        "/api/architecture", response_model=ArchitectureResponse, tags=["Architecture"]
    )
    async def get_architecture():
        """Full architecture model with C4 hierarchy, git, packages, and edges."""
        ws = discover_multi(root)
        raw = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **ws.to_dict(),
            "navigation": ws.to_navigation(),
        }
        return JSONResponse(raw)

    @web_app.get(
        "/api/navigation", response_model=NavigationNode, tags=["Architecture"]
    )
    async def get_navigation():
        """Hierarchical navigation tree for drill-down UI."""
        return JSONResponse(discover_multi(root).to_navigation())

    @web_app.get("/api/systems", response_model=list[SystemInfo], tags=["Architecture"])
    async def list_systems():
        """List all discovered systems with git and package info."""
        ws = discover_multi(root)
        return JSONResponse([_system_dict_from_ws(s) for s in ws.systems])

    @web_app.get(
        "/api/systems/{system_id}", response_model=SystemInfo, tags=["Architecture"]
    )
    async def get_system(system_id: str):
        """Get a single system by ID with full container/component detail."""
        ws = discover_multi(root)
        sys = ws.system_by_id(system_id)
        if not sys:
            return JSONResponse(
                {"detail": f"System '{system_id}' not found"}, status_code=404
            )
        return JSONResponse(_system_dict_from_ws(sys))

    @web_app.get("/api/edges", response_model=list[EdgeInfo], tags=["Architecture"])
    async def list_edges():
        """Cross-system dependency edges from libraries.json."""
        ws = discover_multi(root)
        return JSONResponse(
            [
                {
                    "source": r.source_id,
                    "target": r.target_id,
                    "description": r.description,
                }
                for r in ws.relationships
            ]
        )

    @web_app.get(
        "/api/ports", response_model=list[PortAllocation], tags=["Architecture"]
    )
    async def list_ports():
        """Port allocation table across all systems."""
        ws = discover_multi(root)
        return JSONResponse(ws.all_ports)

    def _system_dict_from_ws(sys):
        from forktex.agent.fsd.arch import _system_dict

        return _system_dict(sys)

    # ── Chat + Tools (MCP-like client-level tool calling) ──

    class ToolDef(BaseModel):
        name: str
        description: str
        endpoint: str
        method: str = "GET"
        parameters: dict = Field(default_factory=dict)

    from fastapi import Request as FastAPIRequest

    # Client-level tool definitions — the MCP surface
    TOOLS: list[dict] = [
        {
            "name": "smart_build_workflow",
            "description": "Generate and deploy a workflow from a natural language description",
            "endpoint": "http://localhost:8002/api/deploy/smart-build",
            "method": "POST",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Natural language workflow description",
                    },
                    "auto_deploy": {"type": "boolean", "default": True},
                },
                "required": ["description"],
            },
        },
        {
            "name": "list_workflows",
            "description": "List all deployed workflows",
            "endpoint": "http://localhost:8002/api/deploy/workflows",
            "method": "GET",
        },
        {
            "name": "get_architecture",
            "description": "Get the full ecosystem architecture with C4 model, git info, and packages",
            "endpoint": f"http://localhost:{port}/api/architecture",
            "method": "GET",
        },
        {
            "name": "list_systems",
            "description": "List all FORKTEX systems with FSD levels",
            "endpoint": f"http://localhost:{port}/api/systems",
            "method": "GET",
        },
        {
            "name": "search_ecosystem",
            "description": "Search the FORKTEX ecosystem knowledge base (RAG)",
            "endpoint": "http://localhost:8001/api/org/{org_id}/search",
            "method": "POST",
        },
    ]

    @web_app.get("/api/tools", response_model=list[ToolDef], tags=["Chat"])
    async def get_tools():
        """Get available MCP-like tool definitions for the AI chat."""
        return JSONResponse(TOOLS)

    @web_app.post("/api/chat", tags=["Chat"])
    async def chat(request: FastAPIRequest):
        """Chat with Intelligence API, with optional tool calling.

        Body: {"messages": [{"role": "user", "content": "..."}], "tools_enabled": true}
        Returns: {"role": "assistant", "content": "...", "tool_calls": [...]}
        """
        body = await request.json()
        messages = body.get("messages", [])
        tools_enabled = body.get("tools_enabled", True)

        from forktex.agent.intelligence.settings import get_intelligence_settings

        settings = get_intelligence_settings()
        if not settings.is_configured:
            return JSONResponse(
                {"detail": "Intelligence API not configured"}, status_code=503
            )

        from forktex_intelligence import Intelligence

        try:
            async with Intelligence() as ai:
                llm_tools = None
                if tools_enabled:
                    llm_tools = [
                        {
                            "name": t["name"],
                            "description": t["description"],
                            "input_schema": t.get(
                                "parameters", {"type": "object", "properties": {}}
                            ),
                        }
                        for t in TOOLS
                    ]

                system = (
                    "You are the FORKTEX factory assistant. You help users build workflows, "
                    "explore architecture, and manage the ecosystem. When the user asks to "
                    "create a workflow, use the smart_build_workflow tool. When they ask about "
                    "the architecture or systems, use list_systems or get_architecture. "
                    "Be concise and helpful."
                )

                resp = await ai.chat(
                    prompt=messages[-1]["content"] if messages else "",
                    messages=messages,
                    system=system,
                    tools=llm_tools,
                )

                return JSONResponse(
                    {
                        "role": "assistant",
                        "content": resp.text,
                        "tool_calls": resp.tool_calls,
                    }
                )
        except Exception as e:
            return JSONResponse(
                {"role": "assistant", "content": f"Error: {e}", "tool_calls": []}
            )

    # Serve React build if provided
    if static_dir and Path(static_dir).is_dir():
        web_app.mount(
            "/app", StaticFiles(directory=static_dir, html=True), name="static"
        )
        click.echo(f"  React: http://{host}:{port}/app")

    # Fallback: serve the Jinja2 HTML dashboard
    @web_app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        return _render_html(discover_multi(root))

    click.echo("FORKTEX Architecture Server")
    click.echo(f"  UI:      http://{host}:{port}/")
    click.echo(f"  API:     http://{host}:{port}/api/architecture")
    click.echo(f"  OpenAPI: http://{host}:{port}/openapi.json")
    click.echo(f"  Docs:    http://{host}:{port}/docs")
    click.echo(f"  Root:    {root}")

    config = uvicorn.Config(web_app, host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()
