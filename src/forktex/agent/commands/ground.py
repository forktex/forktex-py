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

"""forktex agents ground — Refresh project documentation that AI agents read.

Walks the projects in your workspace, reads their manifests and metadata,
and rewrites the per-project markdown briefing the AI assistant uses as
system context.

    forktex agents ground            Refresh briefing for the current project
    forktex agents ground --all      Refresh briefings for every project
    forktex agents ground --status   Show what's discoverable in your workspace
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console, error
from forktex.core.paths import FORKTEX_MANIFEST, find_ecosystem_root


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
            except (json.JSONDecodeError, OSError):  # fmt: skip
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
    """Refresh project documentation across every repo in your workspace."""
    pass


@ground.command(name="status")
@click.option("--dir", "-d", "root_dir", default=None, help="Workspace root directory")
async def ground_status(root_dir: str | None):
    """Show what's discoverable in your workspace: projects, briefings, manifests."""
    if root_dir:
        root = Path(root_dir)
    else:
        root = find_ecosystem_root(Path.cwd())

    if not root or not root.is_dir():
        error("Could not find your workspace root. Use --dir to specify.")
        return

    repos = _discover_repos(root)

    console.print(f"\n[bold]Workspace[/bold] ({root})\n")
    console.print(f"  Found [cyan]{len(repos)}[/cyan] projects:\n")

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
@click.option("--dir", "-d", "root_dir", default=None, help="Workspace root directory")
@click.option("--json-out", is_flag=True, help="Output as JSON")
async def ground_repos(root_dir: str | None, json_out: bool):
    """List all discovered repos with metadata."""
    if root_dir:
        root = Path(root_dir)
    else:
        root = find_ecosystem_root(Path.cwd())

    if not root or not root.is_dir():
        error("Could not find your workspace root. Use --dir to specify.")
        return

    repos = _discover_repos(root)

    if json_out:
        import json as json_mod

        console.print(json_mod.dumps(repos, indent=2))
    else:
        for repo in repos:
            console.print(f"  {_generate_repo_summary(repo)}")


# ─── refresh: regenerate AGENTS.md per project ─────────────────────────


_AGENTS_HEADER = "<!-- forktex-agents:autogen -->"


def _render_agents_md(repo: dict, root: Path) -> str:
    """Render an AGENTS.md body from manifest + filesystem snapshot.

    The output is bounded (~40 lines per project) so an LLM ingesting
    this as context doesn't pay an oversized prompt.
    """
    name = repo["name"]
    repo_path = root / name
    manifest_path = repo_path / "forktex.json"

    description = ""
    packages: list[dict] = []
    target_level = ""
    profiles: list[str] = []
    atoms: list[str] = []
    services: list[str] = repo.get("services", []) or []

    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            data = {}
        description = (data.get("description") or "").strip()
        fsd = data.get("fsd") or {}
        target_level = fsd.get("targetLevel") or ""
        profiles = fsd.get("profiles") or []
        atoms = sorted((fsd.get("atoms") or {}).keys())
        for pkg in data.get("packages") or []:
            packages.append(
                {
                    "name": pkg.get("name", "?"),
                    "path": pkg.get("path", "."),
                    "language": pkg.get("language", "?"),
                    "publishable": bool(pkg.get("publishable", False)),
                }
            )

    make_targets: list[str] = []
    makefile = repo_path / "Makefile"
    if makefile.is_file():
        for line in makefile.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line and ":" in line and not line.startswith(("\t", "#", " ", ".")):
                head = line.split(":", 1)[0].strip()
                if head and "=" not in head and not head.startswith(("-", "$")):
                    if "## " in line:
                        make_targets.append(head)

    lines: list[str] = [
        _AGENTS_HEADER,
        "",
        f"# {name}",
        "",
    ]
    if description:
        lines.extend([description, ""])

    lines.append("## At a glance")
    if profiles:
        lines.append(f"- profiles: {', '.join(profiles)}")
    if target_level:
        lines.append(f"- target FSD level: {target_level}")
    if services:
        lines.append(f"- cloud services: {', '.join(services)}")
    if not (profiles or target_level or services):
        lines.append("- (no FSD or cloud manifest declared)")
    lines.append("")

    if packages:
        lines.append("## Packages")
        for pkg in packages:
            pub = " (publishable)" if pkg["publishable"] else ""
            lines.append(f"- `{pkg['path']}` — {pkg['name']} ({pkg['language']}){pub}")
        lines.append("")

    if make_targets:
        # Cap the displayed list to keep AGENTS.md compact.
        head = make_targets[:20]
        lines.append("## Make targets")
        lines.append(f"`{' · '.join(head)}`")
        if len(make_targets) > 20:
            lines.append(f"_…and {len(make_targets) - 20} more_")
        lines.append("")

    if atoms:
        head = atoms[:15]
        lines.append("## FSD atom overrides")
        lines.append(f"`{' · '.join(head)}`")
        if len(atoms) > 15:
            lines.append(f"_…and {len(atoms) - 15} more_")
        lines.append("")

    lines.append(
        "Refresh this file with `forktex agents ground refresh` "
        "(reads forktex.json + Makefile)."
    )
    lines.append("")
    return "\n".join(lines)


def _is_autogen(path: Path) -> bool:
    """An AGENTS.md is autogen-managed if its first content line is the marker."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        return line == _AGENTS_HEADER
    return False


@ground.command(name="refresh")
@click.option("--dir", "-d", "root_dir", default=None, help="Workspace root directory")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would change without writing",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite even hand-authored AGENTS.md files (dangerous)",
)
async def ground_refresh(root_dir: str | None, dry_run: bool, force: bool):
    """Regenerate AGENTS.md per project from forktex.json + Makefile.

    Idempotent: writes only when the rendered body differs. Skips
    hand-authored AGENTS.md files (those without the autogen marker)
    unless ``--force`` is set; the rendered body always begins with a
    visible marker so authors can opt in by adding it to the top of
    their existing file.
    """
    if root_dir:
        root = Path(root_dir)
    else:
        root = find_ecosystem_root(Path.cwd())

    if not root or not root.is_dir():
        error("Could not find your workspace root. Use --dir to specify.")
        return

    repos = _discover_repos(root)
    written = 0
    skipped_handauthored = 0
    unchanged = 0
    skipped_no_manifest = 0

    for repo in repos:
        if not repo.get("has_forktex_json"):
            skipped_no_manifest += 1
            continue
        repo_path = root / repo["name"]
        agents_path = repo_path / "AGENTS.md"
        new_body = _render_agents_md(repo, root)

        if agents_path.is_file():
            existing = agents_path.read_text(encoding="utf-8", errors="ignore")
            if existing == new_body:
                unchanged += 1
                continue
            if not _is_autogen(agents_path) and not force:
                skipped_handauthored += 1
                console.print(
                    f"  [yellow]skip[/yellow] {repo['name']:<20} "
                    f"AGENTS.md exists and is hand-authored "
                    f"(add `{_AGENTS_HEADER}` at the top to opt in, "
                    "or pass --force)"
                )
                continue

        if dry_run:
            console.print(
                f"  [cyan]would write[/cyan] {repo['name']}/AGENTS.md "
                f"({len(new_body.splitlines())} lines)"
            )
        else:
            agents_path.write_text(new_body, encoding="utf-8")
            console.print(
                f"  [green]✓[/green] {repo['name']:<20} "
                f"AGENTS.md ({len(new_body.splitlines())} lines)"
            )
        written += 1

    console.print()
    if dry_run:
        console.print(
            f"  [bold]Dry run:[/bold] would write {written}, "
            f"unchanged {unchanged}, "
            f"skipped {skipped_handauthored} (hand-authored), "
            f"skipped {skipped_no_manifest} (no forktex.json)"
        )
    else:
        console.print(
            f"  [bold]Refreshed:[/bold] wrote {written}, "
            f"unchanged {unchanged}, "
            f"skipped {skipped_handauthored} (hand-authored), "
            f"skipped {skipped_no_manifest} (no forktex.json)"
        )
