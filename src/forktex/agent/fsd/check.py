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
    ".forktex",
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


def _evaluate(project_root: Path) -> dict:
    """Run the full FSD check and return structured results."""
    root_makefile = project_root / "Makefile"
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
@click.pass_context
async def check(ctx, level, as_json, html_path, output_dir):
    """Verify that a project meets the ForkTex Standard for Delivery."""
    project_root: Path = ctx.obj["project_root"]
    data = _evaluate(project_root)

    # Determine output directory
    out_dir = Path(output_dir) if output_dir else get_fsd_evidence_dir(project_root)

    # Always write JSON + HTML to output dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    json_path = out_dir / f"check-{ts}.json"
    json_path.write_text(json.dumps(data, indent=2))

    html_out = Path(html_path) if html_path else out_dir / f"check-{ts}.html"
    html_out.write_text(_render_html(data))

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
