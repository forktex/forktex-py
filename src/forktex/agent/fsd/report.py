"""forktex fsd report - generate ISO compliance evidence by running quality gates.

Runs the actual Make targets (format-check, lint, test, audit) and captures
their output as structured audit evidence. Outputs JSON + HTML.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncclick as click
from jinja2 import Environment, FileSystemLoader

from forktex.agent.fsd.standard import ISOMapping
from forktex.core.paths import get_fsd_evidence_dir
from forktex.fsd.loader import load_standard

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Quality gates: (make target, label, ISO mappings)
GATES: list[tuple[str, str, list[ISOMapping]]] = [
    ("format-check", "Format Check", [
        ISOMapping("27001", "A.8.26", "Application security requirements"),
        ISOMapping("9001", "8.3.4", "Design and development controls"),
    ]),
    ("lint", "Lint", [
        ISOMapping("27001", "A.8.28", "Secure coding"),
        ISOMapping("9001", "8.3.4", "Design and development controls"),
    ]),
    ("test", "Test", [
        ISOMapping("27001", "A.8.29", "Security testing"),
        ISOMapping("9001", "8.6", "Release of products"),
        ISOMapping("9001", "9.1.1", "Monitoring and measurement"),
    ]),
    ("audit", "Security Audit", [
        ISOMapping("27001", "A.8.8", "Technical vulnerability management"),
    ]),
]


def _run_gate(target: str, label: str, iso: list[ISOMapping], cwd: Path) -> dict:
    """Run a make target and capture output as evidence."""
    start = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            ["make", target], capture_output=True, text=True, cwd=cwd, timeout=300,
        )
        end = datetime.now(timezone.utc)
        return {
            "label": label,
            "command": f"make {target}",
            "exit_code": result.returncode,
            "passed": result.returncode == 0,
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "started_at": start.isoformat(),
            "finished_at": end.isoformat(),
            "duration_seconds": (end - start).total_seconds(),
            "iso_mappings": [{"standard": m.standard, "clause": m.clause, "control": m.control} for m in iso],
        }
    except subprocess.TimeoutExpired:
        return {
            "label": label, "command": f"make {target}", "exit_code": -1, "passed": False,
            "error": "timeout after 300s", "stdout": "", "stderr": "",
            "started_at": start.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 300.0,
            "iso_mappings": [{"standard": m.standard, "clause": m.clause, "control": m.control} for m in iso],
        }
    except FileNotFoundError:
        return {
            "label": label, "command": f"make {target}", "exit_code": -1, "passed": False,
            "error": "make not found", "stdout": "", "stderr": "",
            "started_at": start.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 0.0,
            "iso_mappings": [{"standard": m.standard, "clause": m.clause, "control": m.control} for m in iso],
        }


def _render_html(data: dict) -> str:
    """Render compliance report as HTML via Jinja2."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("report.html")
    return template.render(**data)


@click.command()
@click.option("--output-dir", default=None, type=click.Path(), help="Output directory for evidence")
@click.option("--json-output", "as_json", is_flag=True, help="Output JSON to stdout")
@click.pass_context
async def report(ctx, output_dir, as_json):
    """Generate ISO compliance evidence by running quality gates."""
    project_root: Path = ctx.obj["project_root"]
    out = Path(output_dir) if output_dir else get_fsd_evidence_dir(project_root)
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    gate_results = []
    all_passed = True

    click.echo(f"FSD Compliance Report: {project_root.name}")
    click.echo("=" * 50)

    for target, label, iso in GATES:
        click.echo(f"  Running: {label}... ", nl=False)
        result = _run_gate(target, label, iso, project_root)
        gate_results.append(result)
        if result["passed"]:
            click.echo("PASS")
        else:
            click.echo("FAIL")
            all_passed = False

    # Build ISO evidence matrix from gate results
    iso_evidence = []
    for gate in gate_results:
        for m in gate["iso_mappings"]:
            iso_evidence.append({
                "standard": m["standard"],
                "clause": m["clause"],
                "control": m["control"],
                "gate_label": gate["label"],
                "passed": gate["passed"],
            })

    data = {
        "fsd_version": load_standard().version,
        "project": project_root.name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "overall_passed": all_passed,
        "gates": gate_results,
        "iso_evidence": iso_evidence,
    }

    # Write JSON
    json_path = out / f"report-{ts}.json"
    json_path.write_text(json.dumps(data, indent=2))

    # Write HTML
    html_path = out / f"report-{ts}.html"
    html_path.write_text(_render_html(data))

    click.echo()
    click.echo(f"Overall: {'PASSED' if all_passed else 'FAILED'}")
    click.echo(f"JSON:    {json_path}")
    click.echo(f"HTML:    {html_path}")

    if as_json:
        click.echo()
        click.echo(json.dumps(data, indent=2))

    if not all_passed:
        sys.exit(1)
