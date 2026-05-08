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

"""``forktex clean`` — remove ForkTex's on-disk footprint.

Targets the canonical ``.forktex/`` directories (project + global) and
keeps the registry honest. Driven by the structure spec, so we know
exactly what we're allowed to touch.
"""

from __future__ import annotations

from pathlib import Path

import asyncclick as click
from forktex_cloud import paths as _cloud_paths

from forktex.agent.ui.console import console


_GRAPH_FILES = ("graph.json", "graph.dsl", "graph.html", "c4.html")


def _apply_secure_perms(scope: str, project_root: Path) -> list[Path]:
    """Walk every ``secret``-tagged spec entry and apply 0o600 (POSIX).

    Implements SECURITY.md §A. Returns the list of paths that were
    successfully tightened. No-op on Windows; the spec marks Windows as
    relying on per-user ACLs on ``%APPDATA%``.
    """
    import os
    import sys

    from forktex.graph.structure import secret_entries

    if sys.platform == "win32":
        return []

    candidates: list[Path] = []
    if scope in {"project", "all"}:
        pdir = _cloud_paths.project_dir(project_root)
        for spec in secret_entries("project"):
            if "*" in spec.pattern:
                candidates.extend(p for p in pdir.glob(spec.pattern) if p.is_file())
            else:
                p = pdir / spec.pattern
                if p.is_file():
                    candidates.append(p)
    if scope in {"os", "all"}:
        gdir = _cloud_paths.global_dir()
        for spec in secret_entries("os"):
            if "*" in spec.pattern:
                candidates.extend(p for p in gdir.glob(spec.pattern) if p.is_file())
            else:
                p = gdir / spec.pattern
                if p.is_file():
                    candidates.append(p)

    tightened: list[Path] = []
    for p in candidates:
        try:
            os.chmod(p, 0o600)
            tightened.append(p)
        except OSError:
            console.print(f"[yellow]could not chmod[/yellow] [cyan]{p}[/cyan]")
    return tightened


@click.command("clean")
@click.option(
    "--scope",
    type=click.Choice(["project", "os", "all"], case_sensitive=False),
    default="project",
    show_default=True,
)
@click.option("--project", "-d", default=None, help="Project root (default: cwd)")
@click.option(
    "--missing-only",
    is_flag=True,
    default=False,
    help="Only forget registry entries whose project root no longer exists.",
)
@click.option(
    "--legacy-evidence",
    is_flag=True,
    default=False,
    help="Also remove pre-stable-filename evidence "
    "(`check-*.{json,html}`, `report-*.{json,html}`, `arch-*.*`, "
    "`workspace-*.dsl`) under .forktex/fsd/evidence/.",
)
@click.option(
    "--secure-perms",
    is_flag=True,
    default=False,
    help="Tighten permissions to 0o600 on every secret-tagged file in the "
    "structure spec (POSIX). Implements SECURITY.md §A.",
)
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation.")
async def clean_cmd(
    scope: str,
    project: str | None,
    missing_only: bool,
    legacy_evidence: bool,
    secure_perms: bool,
    yes: bool,
) -> None:
    """Clean up generated artifacts and forget projects that no longer exist."""
    from forktex.graph import registry as _registry

    scope = scope.lower()
    project_root = (Path(project) if project else Path.cwd()).resolve()

    if secure_perms:
        tightened = _apply_secure_perms(scope, project_root)
        if tightened:
            console.print(
                f"[green]✓[/green] tightened permissions on "
                f"[bold]{len(tightened)}[/bold] file(s) to 0o600:"
            )
            for p in tightened:
                console.print(f"  [cyan]{p}[/cyan]")
        else:
            console.print("[dim]no secret-tagged files found needing 0o600.[/dim]")

    targets: list[Path] = []
    if scope in {"project", "all"} and not missing_only:
        pdir = _cloud_paths.project_dir(project_root)
        for fname in _GRAPH_FILES:
            p = pdir / fname
            if p.is_file():
                targets.append(p)
    if scope in {"os", "all"} and not missing_only:
        gdir = _cloud_paths.global_dir()
        for fname in _GRAPH_FILES:
            p = gdir / fname
            if p.is_file():
                targets.append(p)

    if legacy_evidence and scope in {"project", "all"}:
        evidence_dir = _cloud_paths.project_dir(project_root) / "fsd" / "evidence"
        if evidence_dir.is_dir():
            for pattern in (
                "check-*.json",
                "check-*.html",
                "report-*.json",
                "report-*.html",
                "arch-*.json",
                "arch-*.html",
                "arch-*.dsl",
                "workspace-*.dsl",
            ):
                targets.extend(p for p in evidence_dir.glob(pattern) if p.is_file())

    missing_projects: list[str] = []
    if scope in {"os", "all"}:
        _, missing = _registry.reconcile_existence()
        missing_projects = [m.root for m in missing]

    if not targets and not missing_projects:
        console.print("[dim]nothing to clean.[/dim]")
        return

    console.print("[bold]Clean plan:[/bold]")
    for t in targets:
        console.print(f"  remove [cyan]{t}[/cyan]")
    for r in missing_projects:
        console.print(f"  forget registry entry [magenta]{r}[/magenta]")

    if not yes and not click.confirm("Proceed?", default=False):
        console.print("[yellow]aborted.[/yellow]")
        return

    for t in targets:
        try:
            t.unlink()
        except OSError as exc:
            console.print(f"[red]failed[/red] to remove {t}: {exc}")
    for r in missing_projects:
        _registry.forget_project(Path(r))
    console.print("[green]✓[/green] clean complete.")


__all__ = ["clean_cmd"]
