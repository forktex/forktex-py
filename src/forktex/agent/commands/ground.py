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

"""forktex agents ground — Regenerate AGENTS.md from filesystem inspection.

Scans sibling git repositories, reads their forktex.json manifests and
project metadata, and updates AGENTS.md files with current state.

Also provides nested git management utilities:
    forktex agents ground           Regenerate AGENTS.md for current project
    forktex agents ground --all     Regenerate for all sibling projects
    forktex agents ground --status  Show ecosystem status (all repos)
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console, error
from forktex.core.paths import FORKTEX_MANIFEST


def _find_ecosystem_root(start: Path) -> Path | None:
    """Walk up to find the parent directory containing multiple forktex repos."""
    current = start
    for _ in range(5):
        parent = current.parent
        repos = [d for d in parent.iterdir() if d.is_dir() and (d / ".git").is_dir()]
        if len(repos) >= 3:
            return parent
        current = parent
    return None


def _discover_repos(root: Path) -> list[dict]:
    """Discover all forktex repos under the ecosystem root."""
    repos = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not (d / ".git").is_dir():
            continue
        if d.name.startswith("."):
            continue

        repo_info = {
            "name": d.name,
            "path": str(d),
            "has_agents_md": (d / "AGENTS.md").exists(),
            "has_forktex_json": (d / FORKTEX_MANIFEST).exists(),
            "has_makefile": (d / "Makefile").exists(),
            "has_pyproject": (d / "pyproject.toml").exists(),
            "has_package_json": False,
        }

        # Check for forktex.json manifest
        if repo_info["has_forktex_json"]:
            try:
                with open(d / FORKTEX_MANIFEST) as f:
                    manifest = json.load(f)
                cloud_manifest = manifest.get("cloud", manifest)
                repo_info["manifest_name"] = cloud_manifest.get("metadata", {}).get(
                    "name", manifest.get("name", d.name)
                )
                repo_info["services"] = [
                    s.get("id", "?") for s in cloud_manifest.get("services", [])
                ]
                pkg = manifest.get("package")
                if pkg:
                    repo_info["package"] = pkg.get("name")
            except (json.JSONDecodeError, OSError):
                pass

        # Check for client/web subdirectories
        for sub in ["client", "web"]:
            pkg_json = d / sub / "package.json"
            if pkg_json.exists():
                repo_info["has_package_json"] = True
                break

        repos.append(repo_info)

    return repos


def _generate_repo_summary(repo: dict) -> str:
    """Generate a one-line summary for a repo."""
    parts = [repo["name"]]
    if repo.get("services"):
        parts.append(f"services: {', '.join(repo['services'])}")
    if repo.get("package"):
        parts.append(f"package: {repo['package']}")
    flags = []
    if repo["has_agents_md"]:
        flags.append("AGENTS.md")
    if repo["has_makefile"]:
        flags.append("Makefile")
    if flags:
        parts.append(f"[{', '.join(flags)}]")
    return " | ".join(parts)


@click.group()
async def ground():
    """Ecosystem grounding — manage AGENTS.md and nested repos."""
    pass


@ground.command(name="status")
@click.option("--dir", "-d", "root_dir", default=None, help="Ecosystem root directory")
async def ground_status(root_dir: str | None):
    """Show ecosystem status: all repos, their AGENTS.md, manifests, and packages."""
    if root_dir:
        root = Path(root_dir)
    else:
        root = _find_ecosystem_root(Path.cwd())

    if not root or not root.is_dir():
        error("Could not find ecosystem root. Use --dir to specify.")
        return

    repos = _discover_repos(root)

    console.print(f"\n[bold]FORKTEX Ecosystem[/bold] ({root})\n")
    console.print(f"  Found [cyan]{len(repos)}[/cyan] repositories:\n")

    for repo in repos:
        agents_status = (
            "[green]yes[/green]" if repo["has_agents_md"] else "[red]no[/red]"
        )
        manifest_status = (
            "[green]yes[/green]" if repo["has_forktex_json"] else "[dim]no[/dim]"
        )
        pkg = repo.get("package", "")
        pkg_status = f"[cyan]{pkg}[/cyan]" if pkg else "[dim]—[/dim]"

        console.print(
            f"  {repo['name']:<20} "
            f"AGENTS.md: {agents_status:>12}  "
            f"forktex.json: {manifest_status:>12}  "
            f"package: {pkg_status}"
        )

    # Summary
    with_agents = sum(1 for r in repos if r["has_agents_md"])
    with_manifest = sum(1 for r in repos if r["has_forktex_json"])
    with_package = sum(1 for r in repos if r.get("package"))
    console.print(
        f"\n  [bold]Summary:[/bold] {with_agents}/{len(repos)} with AGENTS.md, "
        f"{with_manifest}/{len(repos)} with forktex.json, "
        f"{with_package}/{len(repos)} with packages\n"
    )


@ground.command(name="repos")
@click.option("--dir", "-d", "root_dir", default=None, help="Ecosystem root directory")
@click.option("--json-out", is_flag=True, help="Output as JSON")
async def ground_repos(root_dir: str | None, json_out: bool):
    """List all discovered repos with metadata."""
    if root_dir:
        root = Path(root_dir)
    else:
        root = _find_ecosystem_root(Path.cwd())

    if not root or not root.is_dir():
        error("Could not find ecosystem root. Use --dir to specify.")
        return

    repos = _discover_repos(root)

    if json_out:
        import json as json_mod

        console.print(json_mod.dumps(repos, indent=2))
    else:
        for repo in repos:
            console.print(f"  {_generate_repo_summary(repo)}")
