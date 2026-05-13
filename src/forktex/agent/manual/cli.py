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

"""``forktex manual`` — generate the system-wide architecture + context manual.

Verbs:

- ``forktex manual build [--scope SCOPE]`` — render the bundle.
- ``forktex manual search <keyword>`` — keyword query over the graph.
"""

from __future__ import annotations

from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console
from forktex.core.paths import find_project_root
from forktex.graph.build import build_graph
from forktex.graph.io_proxy import tracked_write
from forktex.graph.models import Graph
from forktex.graph.scopes import ProjectScope
from forktex.manual import (
    ManualBundle,
    ManualScope,
    SearchIndex,
    generate_manual,
)


def _resolve_project_root(project: str | None) -> Path:
    candidate = Path(project).resolve() if project else Path.cwd().resolve()
    found = find_project_root(candidate)
    if found is None:
        raise click.ClickException(
            f"no forktex.json found at or above {candidate}.\n"
            "Run from a project directory or pass --project /path/to/project."
        )
    return found


def _build_project_graph(project_root: Path) -> Graph:
    with console.status("[cyan]building project graph[/cyan]…"):
        return build_graph(ProjectScope(project_root), with_imports=True)


@click.group(invoke_without_command=True)
@click.pass_context
async def manual(ctx):
    """Render an architecture + context manual for humans and AI agents.

    Bundles your project's graph (modules, domains, dependencies) into:

    - ``arch``    — C4 architecture page (system → container → component).
    - ``graph``   — filesystem inspector + dependency tree, single page HTML.
    - ``agents``  — AI-consumable JSON (rules, concepts, few-shots).
    - ``search``  — keyword fuzzy-search over the graph (ranked).

    Default ``forktex manual build`` produces the combined bundle.

    With no subcommand, dispatches to the ``manual`` atom recipe (the
    project's declared `make manual` target). For forktex-py itself
    that loops back to ``forktex manual build``; other projects can
    override the recipe in ``forktex.json``.
    """
    if ctx.invoked_subcommand is not None:
        return
    import sys

    from forktex.agent.atoms.dispatcher import dispatch_atom

    project_root = _resolve_project_root(None)
    rc = dispatch_atom("manual", project_root=project_root)
    sys.exit(rc)


# ── build ─────────────────────────────────────────────────────────────────


_SCOPE_CHOICES = click.Choice(
    [s.value for s in ManualScope],
    case_sensitive=False,
)


@manual.command("build")
@click.option(
    "--scope",
    type=_SCOPE_CHOICES,
    default=ManualScope.DEFAULT.value,
    show_default=True,
    help="Variant scope. `default` combines arch + graph + agents.",
)
@click.option(
    "--project",
    "-d",
    default=None,
    help="Project root (default: walk upward from cwd).",
)
@click.option(
    "--out",
    "-o",
    default=None,
    help="Output directory (default: <project>/.forktex/manual/).",
)
async def build_cmd(scope: str, project: str | None, out: str | None) -> None:
    """Render the manual bundle for the chosen scope."""
    project_root = _resolve_project_root(project)
    scope_enum = ManualScope.from_str(scope)
    out_dir = (
        Path(out).resolve() if out is not None else project_root / ".forktex" / "manual"
    )

    if scope_enum == ManualScope.SEARCH:
        # Search has no rendered artifact; show usage instead of an empty bundle.
        console.print(
            "[yellow]`manual@search` is queried, not built.[/yellow] "
            "Use [cyan]forktex manual search <keyword>[/cyan]."
        )
        return

    graph = _build_project_graph(project_root)
    bundle = generate_manual(graph, scope=scope_enum, project_root=project_root)
    paths = _write_bundle(bundle, out_dir)

    console.print(f"[dim]project root:[/dim] [cyan]{project_root}[/cyan]")
    console.print(
        f"[green]✓[/green] manual @ [bold]{scope_enum.value}[/bold]: "
        f"{bundle.node_count} nodes, {bundle.edge_count} edges"
    )
    for label, path in paths.items():
        console.print(f"  {label}: [cyan]{path}[/cyan]")


def _write_bundle(bundle: ManualBundle, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    if bundle.arch_html:
        path = out_dir / "manual_arch.html"
        tracked_write(path, bundle.arch_html, kind="manual_arch")
        written["arch"] = path
    if bundle.graph_html:
        path = out_dir / "manual_graph.html"
        tracked_write(path, bundle.graph_html, kind="manual_graph")
        written["graph"] = path
    if bundle.rules or bundle.concepts or bundle.few_shots:
        path = out_dir / "manual_agents.json"
        tracked_write(path, bundle.model_dump_json(indent=2), kind="manual_agents")
        written["agents"] = path

    # Always emit a top-level bundle.json with the combined metadata.
    bundle_path = out_dir / "manual_bundle.json"
    tracked_write(bundle_path, bundle.model_dump_json(indent=2), kind="manual_bundle")
    written["bundle"] = bundle_path

    return written


# ── search ────────────────────────────────────────────────────────────────


@manual.command("search")
@click.argument("keyword")
@click.option(
    "--prefix",
    default=None,
    help="Filter by node id prefix (e.g. `file::src/forktex/manual`).",
)
@click.option(
    "--limit",
    "-n",
    type=int,
    default=20,
    show_default=True,
)
@click.option(
    "--project",
    "-d",
    default=None,
    help="Project root (default: walk upward from cwd).",
)
async def search_cmd(
    keyword: str, prefix: str | None, limit: int, project: str | None
) -> None:
    """Keyword search over the project graph (ranked, fast).

    Case-insensitive substring match; multi-keyword AND. Splits the
    query on whitespace.
    """
    project_root = _resolve_project_root(project)
    graph = _build_project_graph(project_root)
    index = SearchIndex(graph)
    hits = index.query(keyword, path_prefix=prefix, limit=limit)

    console.print(f"[dim]project root:[/dim] [cyan]{project_root}[/cyan]")
    if not hits:
        console.print("[yellow]no matches.[/yellow]")
        return
    console.print(
        f"[green]✓[/green] {len(hits)} hit{'s' if len(hits) != 1 else ''} for "
        f"[bold]{keyword!r}[/bold]:\n"
    )
    for hit in hits:
        console.print(
            f"  [cyan]{hit.score:6.2f}[/cyan]  "
            f"[bold]{hit.name}[/bold] "
            f"[dim]({hit.kind})[/dim]"
        )
        console.print(f"          [dim]{hit.snippet}[/dim]")


__all__ = ["manual"]
