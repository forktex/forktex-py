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

"""forktex fsd check - verify a project meets the ForkTex Standard for Delivery.

Outputs: JSON + HTML (dual output by default).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncclick as click
from jinja2 import Environment, FileSystemLoader

from forktex_cloud import paths as _cloud_paths

from forktex.core.paths import get_fsd_evidence_dir
from forktex.fsd.evaluate import AtomStatus, evaluate
from forktex.fsd.loader import (
    ensure_fsd_supported,
    ensure_manifest_supported,
    load_project_config,
    load_standard,
)
from forktex.manifest.models import ForktexManifest

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _find_makefile_targets(makefile_path: Path) -> set[str]:
    """Extract target names from a Makefile."""
    targets: set[str] = set()
    if not makefile_path.exists():
        return targets
    try:
        result = subprocess.run(
            ["make", "-f", str(makefile_path), "-pRrq", "--no-print-directory"],
            capture_output=True,
            text=True,
            cwd=makefile_path.parent,
        )
        for line in result.stdout.splitlines():
            if line and not line.startswith(("\t", ".", "#", " ")) and ":" in line:
                target = line.split(":")[0].strip()
                if target and not target.startswith(("%", "-")):
                    targets.add(target)
    except FileNotFoundError:
        pass
    return targets


SKIP_DIRS = {
    ".git",
    _cloud_paths.PROJECT_DIRNAME,
    ".standard",
    ".github",
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".expo",
    ".next",
}


def _targets_and_services_from_graph(
    graph, project_root: Path
) -> tuple[set[str], list[dict]]:
    """Derive Make targets + service-shaped dicts from a project Graph.

    Each ``package`` node carries ``makefile_targets`` and ``has_makefile``
    in its attrs (added by ``forktex.graph.build``). The root package
    contributes its targets to ``all_targets``; nested packages become
    "services" with their own target sets.
    """
    all_targets: set[str] = set()
    services: list[dict] = []
    for pkg in graph.by_kind("package"):
        rel = pkg.attrs.get("rel_path") or "."
        targets = list(pkg.attrs.get("makefile_targets", []))
        if rel == ".":
            all_targets.update(targets)
        else:
            for t in targets:
                all_targets.add(f"{pkg.name}-{t}")
                all_targets.add(t)
            services.append(
                {
                    "name": pkg.name,
                    "path": str((project_root / rel).resolve()),
                    "targets": sorted(targets),
                    "target_count": len(targets),
                }
            )
    return all_targets, services


def _discover_services(project_root: Path) -> list[dict]:
    """Discover services by looking for subdirectories with Makefiles."""
    services = []
    for d in sorted(project_root.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name in SKIP_DIRS:
            continue
        if d.name.endswith("-data"):  # skip docker volume mounts like network-db-data
            continue
        if not (d / "Makefile").exists():
            continue
        try:
            targets = _find_makefile_targets(d / "Makefile")
        except PermissionError:
            continue
        services.append(
            {
                "name": d.name,
                "path": str(d),
                "targets": sorted(targets),
                "target_count": len(targets),
            }
        )
    return services


def _evaluate(project_root: Path, *, graph=None) -> dict:
    """Run the full FSD check and return structured results.

    Pass ``graph`` (a ``forktex.graph.models.Graph`` from
    ``build_graph(ProjectScope(project_root))``) to skip the duplicate
    Makefile + service walks — the targets and services are read from
    package node attrs instead. Falls back to filesystem walks when no
    graph is provided.
    """
    root_makefile = project_root / "Makefile"
    if graph is not None:
        all_targets, services = _targets_and_services_from_graph(graph, project_root)
    else:
        all_targets = _find_makefile_targets(root_makefile)
        services = _discover_services(project_root)
    manifest = ForktexManifest.load(project_root / "forktex.json")
    ensure_manifest_supported(manifest)
    config = load_project_config(project_root)
    standard = load_standard(
        Path(config.standard_path) if config and config.standard_path else None
    )
    ensure_fsd_supported(standard, config)

    for svc in services:
        for t in svc["targets"]:
            all_targets.add(f"{svc['name']}-{t}")
            all_targets.add(t)

    result = evaluate(
        standard,
        project_root=project_root,
        make_targets=all_targets,
        services=services,
        config=config,
        manifest=manifest,
    )

    # ISO mapping summary
    atom_results = []
    iso_mappings = []
    for atom_result in result.atoms:
        atom = standard.atoms_by_id[atom_result.id]
        status = atom_result.status
        atom_payload = {
            "id": atom.id,
            "name": atom.name,
            "description": atom.description,
            "targets": atom_result.required_targets or atom.make_targets,
            "required_targets": atom_result.required_targets or atom.make_targets,
            "iso": [
                {"standard": m.standard, "clause": m.clause, "control": m.control}
                for m in atom.iso
            ],
            "status": status.value,
            "display_status": "PASS"
            if status == AtomStatus.SATISFIED
            else (
                "SKIP"
                if status == AtomStatus.SKIPPED
                else ("N/A" if status == AtomStatus.OUT_OF_SCOPE else "FAIL")
            ),
            "satisfied": status == AtomStatus.SATISFIED,
            "present_required": atom_result.present_targets,
            "missing_required": atom_result.missing_targets,
            "present_optional": [],
        }
        atom_results.append(atom_payload)
        for m in atom_payload["iso"]:
            iso_mappings.append(
                {
                    "standard": m["standard"],
                    "clause": m["clause"],
                    "control": m["control"],
                    "atom_name": atom.name,
                    "satisfied": status == AtomStatus.SATISFIED,
                }
            )

    return {
        "fsd_version": standard.version,
        "project": project_root.name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "root_makefile": root_makefile.exists(),
        "services": services,
        "atoms": atom_results,
        "levels": [level.__dict__ for level in result.levels],
        "level": result.level,
        "iso_mappings": iso_mappings,
        "satisfied_atoms": result.satisfied_atoms,
        "missing_atoms": result.failed_atoms,
    }


def _render_html(data: dict) -> str:
    """Render the check results as HTML via Jinja2."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("check.html")
    return template.render(**data)


def _enrich_graph_with_fsd_level(project_root: Path, fsd_level: str) -> None:
    """Best-effort: stamp ``fsd_level`` onto the project's package nodes
    in ``.forktex/graph.json`` and re-export DSL/HTML/C4 so downstream
    viewers reflect the freshly-computed level. No-op if the graph hasn't
    been built yet.
    """
    from forktex.graph.build import build_graph
    from forktex.graph.export import export_graph
    from forktex.graph.export.c4_html_writer import render_c4_html
    from forktex.graph.io_proxy import tracked_write
    from forktex.graph.scopes import ProjectScope
    from forktex_cloud import paths as _cp

    try:
        graph = build_graph(ProjectScope(project_root))
        for pkg in graph.by_kind("package"):
            pkg.attrs["fsd_level"] = fsd_level
        export_graph(graph, _cp.project_dir(project_root))
        tracked_write(
            _cp.project_dir(project_root) / "c4.html",
            render_c4_html(graph),
            kind="c4_export",
            writer="forktex.agent.fsd.check",
        )
    except Exception:  # pragma: no cover — non-fatal enrichment
        pass


@click.command()
@click.option(
    "--level", default=None, help="Required level (e.g., L2). Exit non-zero if not met."
)
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON to stdout")
@click.option(
    "--html",
    "html_path",
    default=None,
    type=click.Path(),
    help="Write HTML report to file",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="Write both JSON + HTML to directory",
)
@click.option(
    "--no-enrich-graph",
    is_flag=True,
    default=False,
    help="Skip stamping fsd_level onto the project graph + c4.html.",
)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    default=False,
    help="Also evaluate every nested forktex.json under the project root, "
    "writing per-project evidence into each nested .forktex/fsd/evidence/.",
)
@click.pass_context
async def check(ctx, level, as_json, html_path, output_dir, no_enrich_graph, recursive):
    """Verify that a project meets the ForkTex Standard for Delivery."""
    project_root: Path = ctx.obj["project_root"]
    # Build the graph once and reuse for evaluation + enrichment.
    from forktex.graph.build import build_graph
    from forktex.graph.scopes import ProjectScope

    graph = build_graph(ProjectScope(project_root))
    data = _evaluate(project_root, graph=graph)

    # Determine output directory
    out_dir = Path(output_dir) if output_dir else get_fsd_evidence_dir(project_root)

    # Always write JSON + HTML to output dir using stable filenames; the
    # generated_at field inside the JSON carries the timestamp, and the
    # filesystem mtime preserves it for OS-level tooling.
    out_dir.mkdir(parents=True, exist_ok=True)

    from forktex.graph.io_proxy import tracked_write

    json_path = out_dir / "check.json"
    tracked_write(
        json_path,
        json.dumps(data, indent=2),
        kind="fsd_evidence",
        writer="forktex.agent.fsd.check",
    )

    html_out = Path(html_path) if html_path else out_dir / "check.html"
    tracked_write(
        html_out,
        _render_html(data),
        kind="fsd_evidence",
        writer="forktex.agent.fsd.check",
    )

    if not no_enrich_graph:
        _enrich_graph_with_fsd_level(project_root, data.get("level", "L0"))

    # Console output
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"FSD Compliance Check: {data['project']}")
        click.echo("=" * 50)
        click.echo(f"Root Makefile: {'found' if data['root_makefile'] else 'MISSING'}")
        click.echo(
            f"Services: {', '.join(s['name'] for s in data['services']) or 'none'}"
        )
        click.echo()
        click.echo("Atoms:")
        for atom in data["atoms"]:
            icon = atom["display_status"]
            click.echo(f"  {icon}  {atom['name']}")
            if atom.get("missing_required"):
                click.echo(f"       missing: {', '.join(atom['missing_required'])}")
        click.echo()
        click.echo(f"Maturity Level: {data['level']}")
        click.echo()
        click.echo(f"JSON:  {json_path}")
        click.echo(f"HTML:  {html_out}")

        if level and data["level"] < level:
            click.echo(f"\nFAILED: Required {level}, achieved {data['level']}")
            sys.exit(1)
        elif level:
            click.echo(f"\nPASSED: Required {level}, achieved {data['level']}")

    if recursive:
        from forktex.graph.build import _discover_child_manifests

        nested = _discover_child_manifests(project_root)
        if nested:
            click.echo(f"\n──── recursive: {len(nested)} nested forktex.json found")
        for child_manifest in nested:
            child_root = child_manifest.parent
            try:
                child_data = _evaluate(child_root)
            except Exception as exc:  # pragma: no cover
                click.echo(f"  ✗ {child_root.name}: {exc}")
                continue
            child_evidence_dir = (
                Path(output_dir) if output_dir else get_fsd_evidence_dir(child_root)
            )
            child_evidence_dir.mkdir(parents=True, exist_ok=True)
            tracked_write(
                child_evidence_dir / "check.json",
                json.dumps(child_data, indent=2),
                kind="fsd_evidence",
                writer="forktex.agent.fsd.check",
            )
            tracked_write(
                child_evidence_dir / "check.html",
                _render_html(child_data),
                kind="fsd_evidence",
                writer="forktex.agent.fsd.check",
            )
            atoms_pass = child_data.get("satisfied_atoms", 0)
            atoms_total = atoms_pass + child_data.get("missing_atoms", 0)
            click.echo(
                f"  · {child_root.name:25s} {child_data['level']:6s} "
                f"atoms={atoms_pass}/{atoms_total}"
            )
