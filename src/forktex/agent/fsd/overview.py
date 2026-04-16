"""forktex overview — Generate a full ecosystem overview presentation.

Combines FSD check results + architecture discovery into a single
auto-generated HTML presentation. Collects per-platform evidence and
aggregates it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import asyncclick as click
from jinja2 import Environment, FileSystemLoader

from forktex.agent.fsd.arch_discover import discover_project
from forktex.agent.fsd.check import _find_makefile_targets, _discover_services
from forktex.core.paths import find_project_root, has_manifest
from forktex.agent.fsd.standard import (
    ATOMS,
    FSD_VERSION,
    check_atom_satisfied,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _check_platform(project_root: Path) -> dict:
    """Run FSD check + arch discovery for one platform."""
    # Architecture
    system = discover_project(project_root)

    # FSD targets
    all_targets = _find_makefile_targets(project_root / "Makefile")
    for svc_info in _discover_services(project_root):
        for t in svc_info["targets"]:
            all_targets.add(f"{svc_info['name']}-{t}")
            all_targets.add(t)

    # Atom results
    atoms = []
    passing_ids = set()
    for atom in ATOMS:
        satisfied = check_atom_satisfied(atom.id, all_targets)
        iso_parts = []
        for m in atom.iso:
            iso_parts.append(f"{m.standard}:{m.clause}")
        atoms.append({
            "id": atom.id,
            "name": atom.name,
            "satisfied": satisfied,
            "iso_summary": ", ".join(iso_parts) if iso_parts else "",
        })
        if satisfied:
            passing_ids.add(atom.id)

    return {
        "id": project_root.name,
        "system": system,
        "atoms": atoms,
        "passing_atoms": passing_ids,
        "total_atoms": len(ATOMS),
    }


@click.command("overview")
@click.option("--base-dir", default=None, help="Parent directory containing projects")
@click.argument("projects", nargs=-1)
@click.option("--output-dir", default=None, help="Output directory")
@click.option("--name", default=None, help="Ecosystem name (default: parent dir name)")
async def overview(base_dir, projects, output_dir, name):
    """Generate a full ecosystem overview presentation.

    Combines FSD compliance + C4 architecture into a single HTML.

    Example: forktex overview cloud network intelligence
    """
    if base_dir:
        root = Path(base_dir).resolve()
    else:
        project_root = find_project_root()
        root = project_root.parent if project_root else Path.cwd().resolve()

    project_names = list(projects) if projects else None
    if project_names:
        dirs = [root / n for n in project_names if (root / n).is_dir()]
    else:
        dirs = sorted(d for d in root.iterdir() if d.is_dir() and has_manifest(d))

    eco_name = name or root.name

    click.echo(f"Generating ecosystem overview: {eco_name}")
    click.echo(f"{'=' * 50}")

    # Collect per-platform data
    systems = []
    for d in dirs:
        if not has_manifest(d):
            click.echo(f"  SKIP  {d.name} (no forktex.json)")
            continue
        click.echo(f"  Scanning {d.name}...")
        data = _check_platform(d)
        systems.append(data)
        click.echo(f"    FSD {data['system'].fsd_level} | {len(data['passing_atoms'])}/{data['total_atoms']} atoms | {len(data['system'].containers)} containers")

    if not systems:
        raise click.ClickException("No projects found")

    # Aggregate metrics
    total_containers = sum(len(s["system"].containers) for s in systems)
    all_ports = []
    for s in systems:
        for c in s["system"].containers:
            for p in c.ports:
                tech = c.tech_summary
                all_ports.append({
                    "system": s["system"].name, "service": c.id,
                    "host_port": p.host, "container_port": p.container,
                    "type": c.service_type.value, "tech": tech,
                })
    all_ports.sort(key=lambda x: x["host_port"])

    highest_level = max((s["system"].fsd_level for s in systems), default="L0")
    total_atoms_passing = sum(len(s["passing_atoms"]) for s in systems)

    # ISO mapping aggregation
    all_passing = set()
    any_passing = set()
    for s in systems:
        all_passing &= s["passing_atoms"] if all_passing else set(s["passing_atoms"])
        any_passing |= s["passing_atoms"]

    iso_27001 = []
    iso_9001 = []
    for atom in ATOMS:
        for m in atom.iso:
            entry = {
                "clause": m.clause, "control": m.control, "atom": atom.id,
                "covered": atom.id in all_passing,
                "partial": atom.id in any_passing and atom.id not in all_passing,
            }
            if m.standard == "27001":
                iso_27001.append(entry)
            else:
                iso_9001.append(entry)

    # Render
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    out = Path(output_dir) if output_dir else Path.cwd() / "presentations"
    out.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("ecosystem.html")

    html = template.render(
        name=eco_name,
        fsd_version=FSD_VERSION,
        generated_at=generated_at,
        systems=systems,
        total_containers=total_containers,
        total_ports=len(all_ports),
        highest_level=highest_level,
        total_atoms_passing=total_atoms_passing,
        port_allocation=all_ports,
        iso_27001=iso_27001,
        iso_9001=iso_9001,
    )

    html_path = out / f"ecosystem-overview-{ts}.html"
    html_path.write_text(html)

    # Also write a stable "latest" symlink-style copy
    latest_path = out / "ecosystem-overview.html"
    latest_path.write_text(html)

    # JSON
    json_path = out / f"ecosystem-overview-{ts}.json"
    json_data = {
        "name": eco_name,
        "generated_at": generated_at,
        "fsd_version": FSD_VERSION,
        "systems": [
            {
                "id": s["id"], "name": s["system"].name,
                "fsd_level": s["system"].fsd_level,
                "containers": len(s["system"].containers),
                "atoms_passing": len(s["passing_atoms"]),
                "atoms_total": s["total_atoms"],
            }
            for s in systems
        ],
        "totals": {
            "platforms": len(systems),
            "containers": total_containers,
            "ports": len(all_ports),
            "highest_level": highest_level,
        },
        "port_allocation": all_ports,
    }
    json_path.write_text(json.dumps(json_data, indent=2))

    click.echo()
    click.echo(f"HTML:    {html_path}")
    click.echo(f"Latest:  {latest_path}")
    click.echo(f"JSON:    {json_path}")
