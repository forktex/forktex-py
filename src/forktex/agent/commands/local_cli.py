"""forktex local — Multi-project local environment management.

Start, stop, and manage local environments across forktex projects.
Each project's ports are defined in its forktex.local.json overlay.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import asyncclick as click

from forktex.core.paths import find_project_root, find_projects


def _run(cmd: list[str], cwd: Path) -> int:
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


@click.group("local")
@click.option(
    "--base-dir",
    default=None,
    help="Parent directory containing projects (default: parent of cwd)",
)
@click.pass_context
async def local(ctx, base_dir):
    """Manage local environments across forktex projects."""
    ctx.ensure_object(dict)
    if base_dir:
        ctx.obj["base_dir"] = Path(base_dir).resolve()
    else:
        project_root = find_project_root()
        ctx.obj["base_dir"] = (
            project_root.parent if project_root else Path.cwd().resolve()
        )


@local.command("up")
@click.argument("projects", nargs=-1)
@click.option("--build", is_flag=True, help="Rebuild images")
@click.pass_context
async def up(ctx, projects, build):
    """Start local environments. Specify project names or omit for all.

    Example: forktex local up cloud network intelligence
    """
    base = ctx.obj["base_dir"]
    dirs = find_projects(base, list(projects) if projects else None)

    if not dirs:
        click.echo("No forktex projects found.")
        return

    click.echo(f"Starting {len(dirs)} project(s)...\n")

    for d in dirs:
        click.echo(f"  {d.name}:")

        # Check for forktex.local.json overlay
        has_local = (d / "forktex.local.json").exists()

        if has_local:
            cmd = ["forktex", "cloud", f"--project-dir={d}", "up", "--env", "local", "-d"]
            if build:
                cmd.append("--build")
            rc = _run(cmd, cwd=d)
            if rc == 0:
                click.echo("    started (via forktex cloud up --env local)")
            else:
                click.echo(f"    FAILED (exit {rc})")
        else:
            # Fallback: try make local
            if (d / "Makefile").exists():
                rc = _run(["make", "local"], cwd=d)
                if rc == 0:
                    click.echo("    started (via make local)")
                else:
                    click.echo(f"    FAILED (exit {rc})")
            else:
                click.echo("    SKIP (no forktex.local.json or Makefile)")

        click.echo()


@local.command("down")
@click.argument("projects", nargs=-1)
@click.pass_context
async def down(ctx, projects):
    """Stop local environments."""
    base = ctx.obj["base_dir"]
    dirs = find_projects(base, list(projects) if projects else None)

    for d in dirs:
        has_local = (d / "forktex.local.json").exists()

        if has_local:
            rc = _run(
                [
                    "forktex",
                    "cloud",
                    f"--project-dir={d}",
                    "up",
                    "--env",
                    "local",
                    "--down",
                ],
                cwd=d,
            )
        elif (d / "Makefile").exists():
            rc = _run(["make", "local-down"], cwd=d)
        else:
            rc = -1

        status = "stopped" if rc == 0 else "FAILED" if rc > 0 else "SKIP"
        click.echo(f"  {d.name}: {status}")


@local.command("status")
@click.argument("projects", nargs=-1)
@click.pass_context
async def status(ctx, projects):
    """Show running containers across projects."""
    base = ctx.obj["base_dir"]
    dirs = find_projects(base, list(projects) if projects else None)

    click.echo(f"{'Project':<20} {'Containers':<10} {'Ports'}")
    click.echo("-" * 60)

    for d in dirs:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.compose.project.working_dir={d}",
                "--format",
                "{{.Names}}:{{.Ports}}",
            ],
            capture_output=True,
            text=True,
        )
        # Also try by project name
        if not result.stdout.strip():
            name = d.name.replace("-", "")
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"name={name}",
                    "--format",
                    "{{.Names}}|{{.Ports}}",
                ],
                capture_output=True,
                text=True,
            )

        lines = [l for l in result.stdout.strip().splitlines() if l]
        if lines:
            ports = set()
            for line in lines:
                parts = line.split("|")
                if len(parts) > 1 and parts[1]:
                    for p in parts[1].split(","):
                        p = p.strip()
                        if "->" in p:
                            host_part = p.split("->")[0].split(":")[-1]
                            ports.add(host_part)
            click.echo(
                f"  {d.name:<18} {len(lines):<10} {', '.join(sorted(ports)) or '-'}"
            )
        else:
            click.echo(f"  {d.name:<18} {'0':<10} (not running)")
