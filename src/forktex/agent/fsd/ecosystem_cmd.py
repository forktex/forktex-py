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

"""``forktex fsd ecosystem`` — evaluate FSD compliance across every project
under a parent directory in one shot. Mirrors ``forktex graph ecosystem``
for the FSD compliance dimension.
"""

from __future__ import annotations

from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console


@click.command("ecosystem")
@click.option(
    "--base-dir",
    "-b",
    default=None,
    help="Parent directory holding forktex.json projects "
    "(default: parent of the current project root, else cwd).",
)
@click.option(
    "--include-nested/--top-level-only",
    default=False,
    show_default=True,
    help="Also walk one level deeper for nested forktex.json files.",
)
@click.option(
    "--level",
    default=None,
    help="Required level (e.g., L2). Exit non-zero if any project misses it.",
)
@click.pass_context
async def ecosystem(
    ctx, base_dir: str | None, include_nested: bool, level: str | None
) -> None:
    """Evaluate FSD compliance across every forktex.json project under a directory.

    Discovers projects, runs the FSD check against each, and emits a
    summary table. Per-project JSON+HTML evidence still lands at each
    project's ``.forktex/fsd/evidence/``.
    """
    from forktex.agent.fsd.check import _evaluate
    from forktex.core.paths import find_project_root, find_projects

    if base_dir is not None:
        base = Path(base_dir).resolve()
    else:
        cwd_root = find_project_root(Path.cwd())
        base = (cwd_root.parent if cwd_root else Path.cwd()).resolve()

    if not base.is_dir():
        raise click.ClickException(f"base directory not found: {base}")

    candidates = list(find_projects(base))
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

    console.print(f"[dim]ecosystem base:[/dim] [cyan]{base}[/cyan]")
    console.print(
        f"[dim]evaluating[/dim] [bold]{len(candidates)}[/bold] [dim]projects[/dim]"
    )

    results: list[dict] = []
    for project_root in candidates:
        with console.status(
            f"[cyan]evaluating[/cyan] [bold]{project_root.name}[/bold]…",
            spinner="dots",
        ):
            try:
                data = _evaluate(project_root)
            except Exception as exc:  # pragma: no cover
                console.print(
                    f"  [red]✗[/red] {project_root.name} — {type(exc).__name__}: {exc}"
                )
                continue
        results.append({"project": project_root, "data": data})

    if not results:
        console.print("[yellow]no projects evaluated successfully.[/yellow]")
        return

    # Summary table.
    console.print()
    console.print(
        f"[bold]{'PROJECT':25s} {'LEVEL':8s} {'ATOMS':10s} {'SERVICES':10s}[/bold]"
    )
    console.print("─" * 60)
    failures: list[str] = []
    for r in results:
        d = r["data"]
        sat = d.get("satisfied_atoms", [])
        miss = d.get("missing_atoms", [])
        atoms_passed = len(sat) if isinstance(sat, list) else int(sat or 0)
        atoms_missing = len(miss) if isinstance(miss, list) else int(miss or 0)
        atoms_total = atoms_passed + atoms_missing
        atoms_str = f"{atoms_passed}/{atoms_total}"
        services_str = str(len(d.get("services", [])))
        lvl = d.get("level", "L0")
        ok = (level is None) or (lvl >= level)
        marker = "[green]✓[/green]" if ok else "[red]✗[/red]"
        if not ok:
            failures.append(r["project"].name)
        console.print(
            f"{marker} {r['project'].name:23s} {lvl:8s} {atoms_str:10s} {services_str:10s}"
        )

    console.print()
    console.print(
        "[dim]individual evidence:[/dim] [cyan]<project>/.forktex/fsd/evidence/[/cyan]"
    )

    if level and failures:
        raise click.ClickException(
            f"{len(failures)} project(s) below required level {level}: "
            f"{', '.join(failures)}"
        )
