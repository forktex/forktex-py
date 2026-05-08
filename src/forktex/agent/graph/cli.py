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

"""``forktex graph`` — build, show, serve, purge the source-of-truth graph."""

from __future__ import annotations

from pathlib import Path

import asyncclick as click
from forktex_cloud import paths as _cloud_paths
from rich.tree import Tree

from forktex.agent.ui.console import console
from forktex.core.paths import find_project_root
from forktex.graph import structure
from forktex.graph.build import build_graph
from forktex.graph.export import export_graph
from forktex.graph.export.c4_html_writer import render_c4_html
from forktex.graph.export.dsl_writer import render_dsl
from forktex.graph.export.json_writer import render_json
from forktex.graph.io_proxy import tracked_write
from forktex.graph.models import Graph
from forktex.graph.scopes import OSScope, ProjectScope


SCOPE_CHOICES = click.Choice(["project", "os", "all"], case_sensitive=False)
FORMAT_CHOICES = click.Choice(["tree", "dsl", "json"], case_sensitive=False)
SCOPE_SHOW_CHOICES = click.Choice(["project", "os"], case_sensitive=False)


__all__ = ["graph"]


# ── Helpers ───────────────────────────────────────────────────────────────


def _resolve_project_root(project: str | None) -> Path:
    """Resolve a project root, walking upward to find a forktex.json.

    Without this, a project-scope build invoked from outside any project
    (e.g. ``$HOME``) would ``rglob`` the entire tree looking for
    forktex.json files and take effectively forever. We refuse instead.

    Also fires the runtime lifecycle (auto-install + instance record) for
    the resolved project, so graph commands appear in the live registry.
    """
    explicit = Path(project).resolve() if project else None
    candidate = explicit or Path.cwd().resolve()
    found = find_project_root(candidate)
    if found is None:
        raise click.ClickException(
            f"no forktex.json found at or above {candidate}.\n"
            "Run from a project directory, pass --project /path/to/project, "
            "or use `--scope os` for the host-wide graph."
        )
    from forktex.runtime.lifecycle import ensure_runtime

    ensure_runtime(needs_project=True, kind="graph", project_hint=str(found))
    return found


def _build_project_with_status(
    project_root: Path, *, with_imports: bool = True
) -> Graph:
    label = (
        "[cyan]building project graph[/cyan]"
        if with_imports
        else "[cyan]building project graph (no imports)[/cyan]"
    )
    with console.status(f"{label} from [dim]{project_root}[/dim]…", spinner="dots"):
        return build_graph(ProjectScope(project_root), with_imports=with_imports)


def _build_os_with_status() -> Graph:
    with console.status(
        f"[cyan]building OS graph[/cyan] from [dim]{_cloud_paths.global_dir()}[/dim]…",
        spinner="dots",
    ):
        return build_graph(OSScope())


def _build_for_scope(
    scope: str, project_root: Path | None, *, with_imports: bool = True
) -> dict[str, Graph]:
    out: dict[str, Graph] = {}
    if scope in {"project", "all"}:
        if project_root is None:
            raise click.ClickException(
                "project-scope build requires a project root; "
                "see `--scope os` for host-wide builds."
            )
        out["project"] = _build_project_with_status(
            project_root, with_imports=with_imports
        )
    if scope in {"os", "all"}:
        out["os"] = _build_os_with_status()
    return out


def _project_out_dir(project_root: Path) -> Path:
    return _cloud_paths.project_dir(project_root)


def _os_out_dir() -> Path:
    return _cloud_paths.global_dir()


def _resolve_and_graph(
    project: str | None,
    *,
    with_imports: bool = True,
    show_header: bool = True,
    cached: bool = False,
) -> tuple[Path, Graph]:
    """Resolve the project root and return ``(root, graph)`` ready for use.

    By default builds a fresh project graph with a status spinner. With
    ``cached=True``, returns the per-process cached graph (faster for
    ad-hoc queries); ``with_imports`` is ignored in that mode. Prints
    the standard ``project root: …`` header unless ``show_header=False``.
    """
    project_root = _resolve_project_root(project)
    if show_header:
        console.print(
            f"[dim]project root:[/dim] [cyan]{project_root}[/cyan]",
            highlight=False,
        )
    if cached:
        from forktex.graph.query import session_graph

        graph_obj = session_graph(project_root)
    else:
        graph_obj = _build_project_with_status(project_root, with_imports=with_imports)
    return project_root, graph_obj


# ── graph ─────────────────────────────────────────────────────────────────


@click.group()
def graph():
    """Inspect your project's structure as a queryable graph.

    Builds a typed map of your packages, domains, modules, libraries,
    and their import + dependency relationships. Use ``build`` to
    refresh, ``show`` to render a tree, ``c4`` for an architecture
    drill-down, ``importers`` / ``modules`` / ``package`` / ``recent``
    for ad-hoc questions, ``ecosystem`` to walk every project under a
    parent directory, and ``diff`` to compare two snapshots.
    """


# ── build ─────────────────────────────────────────────────────────────────


@graph.command("build")
@click.option("--scope", type=SCOPE_CHOICES, default="project", show_default=True)
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
@click.option(
    "--imports/--no-imports",
    default=True,
    show_default=True,
    help="Run the AST imports pass (off speeds large monorepos significantly).",
)
async def build_cmd(scope: str, project: str | None, imports: bool) -> None:
    """Build and write ``graph.{json,dsl,html}`` for the chosen scope."""
    scope = scope.lower()
    project_root: Path | None = None
    if scope in {"project", "all"}:
        project_root = _resolve_project_root(project)
        console.print(f"[dim]project root:[/dim] [cyan]{project_root}[/cyan]")

    graphs = _build_for_scope(scope, project_root, with_imports=imports)

    if "project" in graphs and project_root is not None:
        out_dir = _project_out_dir(project_root)
        with console.status("[cyan]writing project graph exports[/cyan]…"):
            paths = export_graph(graphs["project"], out_dir)
        console.print(
            f"[green]✓[/green] project graph: "
            f"{len(graphs['project'].nodes)} nodes, "
            f"{len(graphs['project'].edges)} edges → "
            f"[cyan]{paths.json_path}[/cyan]"
        )
    if "os" in graphs:
        out_dir = _os_out_dir()
        with console.status("[cyan]writing OS graph exports[/cyan]…"):
            paths = export_graph(graphs["os"], out_dir)
        console.print(
            f"[green]✓[/green] OS graph: "
            f"{len(graphs['os'].nodes)} nodes, "
            f"{len(graphs['os'].edges)} edges → "
            f"[cyan]{paths.json_path}[/cyan]"
        )


# ── show ──────────────────────────────────────────────────────────────────


def _render_tree(graph_obj: Graph) -> Tree:
    label = (
        f"[bold]{graph_obj.meta.scope}[/bold] · {graph_obj.meta.root} "
        f"[dim]({len(graph_obj.nodes)} nodes / {len(graph_obj.edges)} edges)[/dim]"
    )
    root = Tree(label)

    by_kind: dict[str, list] = {}
    for node in graph_obj.nodes:
        by_kind.setdefault(node.kind, []).append(node)
    for kind in sorted(by_kind):
        kind_branch = root.add(f"[cyan]{kind}[/cyan] ({len(by_kind[kind])})")
        for node in sorted(by_kind[kind], key=lambda n: n.name)[:25]:
            rel = node.attrs.get("rel_path") or node.attrs.get("abs_path") or ""
            label = node.name + (f" [dim]— {rel}[/dim]" if rel else "")
            kind_branch.add(label)
        if len(by_kind[kind]) > 25:
            kind_branch.add(f"[dim]… {len(by_kind[kind]) - 25} more[/dim]")
    return root


@graph.command("show")
@click.option("--format", "fmt", type=FORMAT_CHOICES, default="tree", show_default=True)
@click.option("--scope", type=SCOPE_SHOW_CHOICES, default="project", show_default=True)
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
async def show_cmd(fmt: str, scope: str, project: str | None) -> None:
    """Render the graph as a tree, JSON, or Structurizr DSL on stdout."""
    fmt = fmt.lower()
    scope = scope.lower()
    if scope == "project":
        _, graph_obj = _resolve_and_graph(project)
    else:
        graph_obj = _build_os_with_status()

    if fmt == "tree":
        console.print(_render_tree(graph_obj))
    elif fmt == "json":
        click.echo(render_json(graph_obj))
    else:
        click.echo(render_dsl(graph_obj))


# ── ecosystem ─────────────────────────────────────────────────────────────


@graph.command("ecosystem")
@click.option(
    "--base-dir",
    "-b",
    default=None,
    help="Parent directory holding forktex.json projects "
    "(default: parent of the current project root, else cwd).",
)
@click.option(
    "--render",
    type=click.Choice(["tree", "c4", "json", "all"], case_sensitive=False),
    default="tree",
    show_default=True,
    help="What to emit after the ecosystem walk.",
)
@click.option(
    "--include-nested/--top-level-only",
    default=False,
    show_default=True,
    help="Also walk one level deeper for nested forktex.json files "
    "(e.g., cloud/sdk-py inside cloud/).",
)
@click.option(
    "--per-project/--unified",
    default=False,
    show_default=True,
    help="With --render c4: also emit one c4.html per project into "
    "each <project>/.forktex/, in addition to the unified host c4.html.",
)
async def ecosystem_cmd(
    base_dir: str | None,
    render: str,
    include_nested: bool,
    per_project: bool,
) -> None:
    """Inspect every forktex.json project under a parent directory in one shot.

    Discovers the projects, ensures each is registered (auto-installs
    .forktex/ + writes a registry entry), then builds the unified host
    graph. Default render is a `rich` tree of registered_project nodes;
    use ``--render c4`` for a drill-down HTML report at
    ``~/.forktex/c4.html`` covering the whole ecosystem.
    """
    from forktex.core.paths import find_projects, find_project_root

    if base_dir is not None:
        base = Path(base_dir).resolve()
    else:
        cwd_root = find_project_root(Path.cwd())
        base = (cwd_root.parent if cwd_root else Path.cwd()).resolve()

    if not base.is_dir():
        raise click.ClickException(f"base directory not found: {base}")

    console.print(f"[dim]ecosystem base:[/dim] [cyan]{base}[/cyan]")

    candidates = find_projects(base)
    if include_nested:
        for child in list(candidates):
            for grandchild in child.iterdir() if child.is_dir() else []:
                if grandchild.is_dir() and (grandchild / "forktex.json").is_file():
                    candidates.append(grandchild)
    candidates = sorted({c.resolve() for c in candidates})

    if not candidates:
        console.print(
            f"[yellow]no forktex.json projects under[/yellow] [cyan]{base}[/cyan]"
        )
        return

    console.print(
        f"[dim]discovered[/dim] [bold]{len(candidates)}[/bold] [dim]projects[/dim]"
    )

    project_graphs: dict[Path, Graph] = {}
    with console.status(
        "[cyan]registering + building each project[/cyan]…", spinner="dots"
    ):
        for project_root in candidates:
            try:
                project_graphs[project_root] = build_graph(ProjectScope(project_root))
            except Exception as exc:  # pragma: no cover
                console.print(f"  [red]✗[/red] {project_root.name} — {exc}")

    g_os = _build_os_with_status()

    if render in {"tree", "all"}:
        console.print(_render_tree(g_os))
    if render in {"c4", "all"}:
        from forktex.graph.export.c4_html_writer import render_c4_html

        # Always emit the unified host-wide C4.
        target = _os_out_dir() / "c4.html"
        tracked_write(
            target,
            render_c4_html(g_os),
            kind="c4_export",
            writer="forktex.agent.graph.cli",
        )
        console.print(f"[green]✓[/green] ecosystem C4 → [cyan]{target}[/cyan]")
        # Optionally emit per-project C4 into each project's .forktex/.
        if per_project:
            for project_root, g in project_graphs.items():
                per_target = _project_out_dir(project_root) / "c4.html"
                try:
                    tracked_write(
                        per_target,
                        render_c4_html(g),
                        kind="c4_export",
                        writer="forktex.agent.graph.cli",
                    )
                    console.print(
                        f"  [green]✓[/green] {project_root.name:18s} → "
                        f"[cyan]{per_target}[/cyan]"
                    )
                except Exception as exc:  # pragma: no cover
                    console.print(f"  [red]✗[/red] {project_root.name} — {exc}")
    if render in {"json", "all"}:
        click.echo(render_json(g_os))


# ── c4 ────────────────────────────────────────────────────────────────────


@graph.command("c4")
@click.option("--scope", type=SCOPE_SHOW_CHOICES, default="project", show_default=True)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["dsl", "html"], case_sensitive=False),
    default="dsl",
    show_default=True,
    help="dsl prints to stdout; html writes a per-platform C4 page.",
)
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
@click.option(
    "--out",
    type=click.Path(),
    default=None,
    help="Output path. With --format html, defaults to <scope-root>/.forktex/c4.html.",
)
async def c4_cmd(scope: str, fmt: str, project: str | None, out: str | None) -> None:
    """Per-platform C4 view (DSL on stdout or a focused HTML page).

    The C4 projection treats each package as a SoftwareSystem, each
    domain as a Container, and each module as a Component — the same
    deliverable the legacy ``forktex arch`` produced, now read from the
    source-of-truth graph.
    """
    fmt = fmt.lower()
    scope = scope.lower()
    if scope == "project":
        project_root, graph_obj = _resolve_and_graph(project)
        default_out = _project_out_dir(project_root) / "c4.html"
    else:
        graph_obj = _build_os_with_status()
        default_out = _os_out_dir() / "c4.html"

    if fmt == "dsl":
        if out:
            tracked_write(
                Path(out),
                render_dsl(graph_obj),
                kind="c4_export",
                writer="forktex.agent.graph.cli",
            )
            console.print(f"[green]✓[/green] DSL → [cyan]{out}[/cyan]")
        else:
            click.echo(render_dsl(graph_obj))
    else:
        target = Path(out) if out else default_out
        with console.status("[cyan]rendering C4 HTML[/cyan]…"):
            tracked_write(
                target,
                render_c4_html(graph_obj),
                kind="c4_export",
                writer="forktex.agent.graph.cli",
            )
        console.print(f"[green]✓[/green] C4 HTML → [cyan]{target}[/cyan]")


# ── audit ─────────────────────────────────────────────────────────────────


@graph.command("audit")
@click.option("--scope", type=SCOPE_SHOW_CHOICES, default="project", show_default=True)
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit non-zero if any unknown or missing-required entry is found "
    "(use as a CI gate; see SECURITY.md §B).",
)
async def audit_cmd(scope: str, project: str | None, strict: bool) -> None:
    """Audit ``.forktex/`` directories against the canonical structure spec.

    For project scope, every nested ``.forktex/`` reachable under the
    project root is audited (a monorepo with N nested forktex projects
    yields N reports — each footprint is its own legal/integrity unit).
    Pass ``--strict`` to make the command a CI gate.
    """
    scope_l = scope.lower()
    findings = {"unknown": 0, "missing": 0}

    def _print_report(label: str, entries: list[structure.AuditEntry]) -> None:
        matched = [r for r in entries if r.status == "matched"]
        unknown = [r for r in entries if r.status == "unknown"]
        missing = [r for r in entries if r.status == "missing_required"]
        findings["unknown"] += len(unknown)
        findings["missing"] += len(missing)
        console.print(
            f"[bold]{label}[/bold]: "
            f"[green]{len(matched)} matched[/green] · "
            f"[yellow]{len(unknown)} unknown[/yellow] · "
            f"[red]{len(missing)} missing[/red]"
        )
        for r in unknown:
            console.print(f"  [yellow]?[/yellow] {r.rel_path} — {r.reason}")
        for r in missing:
            purpose = r.spec.purpose if r.spec else ""
            console.print(f"  [red]✗[/red] {r.rel_path} — required ({purpose})")

    if scope_l == "project":
        project_root = _resolve_project_root(project)
        with console.status(
            f"[cyan]discovering nested .forktex/ under[/cyan] "
            f"[dim]{project_root}[/dim]…",
            spinner="dots",
        ):
            reports = structure.audit_tree(project_root)
        if not reports:
            console.print(
                f"[dim]no .forktex/ directory found under[/dim] "
                f"[cyan]{project_root}[/cyan]"
            )
            return
        if len(reports) > 1:
            console.print(
                f"[dim]auditing {len(reports)} nested .forktex/ directories[/dim]"
            )
        for report in reports:
            try:
                rel = report.project_root.relative_to(project_root).as_posix()
            except ValueError:
                rel = str(report.project_root)
            label = f"project {rel}" if rel != "." else "project"
            _print_report(label, report.entries)
    else:
        entries = structure.audit("os", _cloud_paths.global_dir())
        _print_report("os", entries)

    if strict and (findings["unknown"] or findings["missing"]):
        raise click.ClickException(
            f"strict audit failed: {findings['unknown']} unknown, "
            f"{findings['missing']} missing-required entries"
        )


# ── diff ──────────────────────────────────────────────────────────────────


def _load_graph_json(path: Path) -> dict:
    import json

    if not path.is_file():
        raise click.ClickException(f"graph JSON not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"could not parse {path}: {exc}") from exc


def _diff_collections(before: list[dict], after: list[dict], key: str) -> dict:
    before_keys = {item[key] for item in before}
    after_keys = {item[key] for item in after}
    added_keys = after_keys - before_keys
    removed_keys = before_keys - after_keys
    return {
        "added": [it for it in after if it[key] in added_keys],
        "removed": [it for it in before if it[key] in removed_keys],
        "kept": len(before_keys & after_keys),
    }


@graph.command("diff")
@click.argument(
    "before",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "after",
    type=click.Path(dir_okay=False, path_type=Path),
    required=False,
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["tree", "json"], case_sensitive=False),
    default="tree",
    show_default=True,
)
async def diff_cmd(before: Path, after: Path | None, fmt: str) -> None:
    """Diff two ``graph.json`` snapshots, surfacing added/removed nodes + edges.

    With one positional argument, compares ``BEFORE`` against the current
    project's freshly-built graph (so you can stash an old export and see
    what changed since). With two arguments, compares the two files
    directly.
    """
    fmt = fmt.lower()
    before_data = _load_graph_json(before)
    if after is not None:
        after_data = _load_graph_json(after)
        after_label = str(after)
    else:
        project_root, graph_obj = _resolve_and_graph(None, show_header=False)
        import json as _json

        after_data = _json.loads(render_json(graph_obj))
        after_label = f"<live: {project_root}>"

    nodes_diff = _diff_collections(
        before_data.get("nodes", []), after_data.get("nodes", []), "id"
    )
    edges_diff = _diff_collections(
        before_data.get("edges", []), after_data.get("edges", []), "id"
    )

    if fmt == "json":
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "before": str(before),
                    "after": after_label,
                    "nodes": nodes_diff,
                    "edges": edges_diff,
                },
                indent=2,
            )
        )
        return

    console.print(f"[dim]before:[/dim] [cyan]{before}[/cyan]")
    console.print(f"[dim]after :[/dim] [cyan]{after_label}[/cyan]")
    console.print()

    def _fmt_node(item: dict) -> str:
        attrs = item.get("attrs") or {}
        rel = attrs.get("rel_path") or attrs.get("abs_path") or ""
        suffix = f" — {rel}" if rel else ""
        return f"[{item['kind']}] {item.get('name', '?')}{suffix}"

    def _fmt_edge(item: dict) -> str:
        return f"[{item['kind']}] {item['src_id']} → {item['dst_id']}"

    def _section(title: str, items: list[dict], fmt_fn) -> None:
        if not items:
            return
        console.print(f"[bold]{title}[/bold] ({len(items)})")
        for item in items[:30]:
            console.print(f"  {fmt_fn(item)}")
        if len(items) > 30:
            console.print(f"  [dim]… +{len(items) - 30} more[/dim]")
        console.print()

    n_added = len(nodes_diff["added"])
    n_removed = len(nodes_diff["removed"])
    e_added = len(edges_diff["added"])
    e_removed = len(edges_diff["removed"])
    console.print(
        f"[bold]nodes[/bold] +{n_added} / -{n_removed} ({nodes_diff['kept']} unchanged)"
    )
    console.print(
        f"[bold]edges[/bold] +{e_added} / -{e_removed} ({edges_diff['kept']} unchanged)"
    )
    console.print()

    _section("[green]+ nodes added[/green]", nodes_diff["added"], _fmt_node)
    _section("[red]- nodes removed[/red]", nodes_diff["removed"], _fmt_node)
    _section("[green]+ edges added[/green]", edges_diff["added"], _fmt_edge)
    _section("[red]- edges removed[/red]", edges_diff["removed"], _fmt_edge)


# ── ad-hoc query shortcuts ────────────────────────────────────────────────


@graph.command("importers")
@click.argument("target")
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
async def importers_cmd(target: str, project: str | None) -> None:
    """List modules in the project that import TARGET (a library, sibling
    package, or in-project dotted name like ``forktex.graph.io_proxy``)."""
    from forktex.graph.query import importers_of

    _, graph_obj = _resolve_and_graph(project, show_header=False, cached=True)
    edges = importers_of(graph_obj, target)
    if not edges:
        console.print(f"[dim]no modules import[/dim] [cyan]{target}[/cyan]")
        return
    console.print(
        f"[dim]importers of[/dim] [cyan]{target}[/cyan] [dim]({len(edges)})[/dim]"
    )
    for edge in edges:
        console.print(f"  · {edge.src_module}")


@graph.command("package")
@click.argument("rel_path", required=False, default=".")
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
async def package_cmd(rel_path: str, project: str | None) -> None:
    """Locate the package containing REL_PATH (defaults to the project root)."""
    from forktex.graph.query import find_package_by_path

    _, graph_obj = _resolve_and_graph(project, show_header=False, cached=True)
    pkg = find_package_by_path(graph_obj, rel_path)
    if pkg is None:
        console.print(f"[yellow]no package contains[/yellow] [cyan]{rel_path}[/cyan]")
        return
    console.print(
        f"[cyan]{rel_path}[/cyan] [dim]→[/dim] [bold]{pkg.name}[/bold] ({pkg.rel_path})"
    )
    console.print(
        f"  [dim]fsd_level={pkg.fsd_level}  domains={pkg.domain_count}  "
        f"modules={pkg.module_count}  has_makefile={pkg.has_makefile}[/dim]"
    )


@graph.command("modules")
@click.argument("name_pattern")
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
async def modules_cmd(name_pattern: str, project: str | None) -> None:
    """Find modules whose name or dotted name matches NAME_PATTERN (glob)."""
    from forktex.graph.query import find_modules

    _, graph_obj = _resolve_and_graph(project, show_header=False, cached=True)
    matches = find_modules(graph_obj, name_pattern)
    if not matches:
        console.print(f"[dim]no modules matching[/dim] [cyan]{name_pattern}[/cyan]")
        return
    for module in matches[:50]:
        dotted = f" [dim]({module.dotted_name})[/dim]" if module.dotted_name else ""
        console.print(f"  · {module.rel_path}{dotted}")
    if len(matches) > 50:
        console.print(f"  [dim]… +{len(matches) - 50} more[/dim]")


@graph.command("recent")
@click.option(
    "--hours", default=24, show_default=True, type=int, help="Time window in hours"
)
@click.option(
    "--project",
    "-d",
    default=None,
    help="Project root (default: all registered projects)",
)
async def recent_cmd(hours: int, project: str | None) -> None:
    """Files inside ``.forktex/`` touched in the last N hours, with attribution.

    Without ``--project``, scans every registered project plus the global
    ``~/.forktex/`` writes.
    """
    from forktex.graph.query import files_touched_recently

    project_root = Path(project).resolve() if project else None
    touches = files_touched_recently(project_root, hours=hours)
    if not touches:
        console.print(
            f"[dim]no .forktex/ writes in the last[/dim] [cyan]{hours}h[/cyan]"
        )
        return
    console.print(f"[dim]{len(touches)} writes in the last[/dim] [cyan]{hours}h[/cyan]")
    for touch in touches[:60]:
        console.print(
            f"  [dim]{touch.last_touched_at}[/dim]  "
            f"[bold]{touch.kind}[/bold]  "
            f"{touch.project_root}/.forktex/{touch.rel_path}  "
            f"[dim]({touch.writer or '?'})[/dim]"
        )
    if len(touches) > 60:
        console.print(f"  [dim]… +{len(touches) - 60} more[/dim]")
