"""forktex git — Direct git operations across projects.

Provides CLI wrappers around the git agent tools for multi-project operations.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncclick as click

from forktex.agent.tools.git import (
    _git_branch, _git_checkout, _git_status, _git_branch_list,
)


@click.group()
@click.pass_context
async def git(ctx):
    """Git operations across forktex projects."""
    ctx.ensure_object(dict)


@git.command("branch-all")
@click.argument("branch_name")
@click.option("--projects", "-p", multiple=True, help="Project directories (default: auto-detect siblings)")
@click.option("--base-dir", default=None, help="Parent directory containing projects")
@click.option("--checkout/--no-checkout", default=True, help="Checkout after creating")
async def branch_all(branch_name, projects, base_dir, checkout):
    """Create a branch across multiple projects.

    Example: forktex git branch-all forktex-standard -p docs -p cloud -p network
    """
    if base_dir:
        root = Path(base_dir).resolve()
    else:
        root = Path.cwd().parent if Path.cwd().name != "forktex" else Path.cwd()

    if projects:
        dirs = [root / p for p in projects]
    else:
        # Auto-detect: all sibling directories that are git repos
        dirs = sorted(
            d for d in root.iterdir()
            if d.is_dir() and (d / ".git").exists()
        )

    for d in dirs:
        if not d.exists():
            click.echo(f"  SKIP  {d.name} (not found)")
            continue
        if not (d / ".git").exists():
            click.echo(f"  SKIP  {d.name} (not a git repo)")
            continue

        result = await _git_status(str(d))
        current = result.data.get("branch", "unknown") if result.data else "unknown"

        # Check if branch already exists
        branches_result = await _git_branch_list(str(d))
        existing = branches_result.data.get("branches", []) if branches_result.data else []

        if branch_name in existing:
            if checkout:
                r = await _git_checkout(str(d), branch_name)
                click.echo(f"  EXISTS  {d.name}: already has '{branch_name}', checked out")
            else:
                click.echo(f"  EXISTS  {d.name}: already has '{branch_name}'")
        else:
            r = await _git_branch(str(d), branch_name, checkout)
            if r.is_error:
                click.echo(f"  FAIL  {d.name}: {r.content}")
            else:
                click.echo(f"  OK    {d.name}: {current} → {branch_name}")


@git.command("status-all")
@click.option("--projects", "-p", multiple=True, help="Project directories")
@click.option("--base-dir", default=None, help="Parent directory containing projects")
async def status_all(projects, base_dir):
    """Show git status across multiple projects."""
    if base_dir:
        root = Path(base_dir).resolve()
    else:
        root = Path.cwd().parent if Path.cwd().name != "forktex" else Path.cwd()

    if projects:
        dirs = [root / p for p in projects]
    else:
        dirs = sorted(
            d for d in root.iterdir()
            if d.is_dir() and (d / ".git").exists()
        )

    for d in dirs:
        if not d.exists() or not (d / ".git").exists():
            continue
        result = await _git_status(str(d))
        if result.data:
            data = result.data
            branch = data.get("branch", "?")
            staged = len(data.get("staged", []))
            modified = len(data.get("modified", []))
            untracked = len(data.get("untracked", []))
            status = "clean" if (staged + modified + untracked) == 0 else f"S:{staged} M:{modified} U:{untracked}"
            click.echo(f"  {d.name:<20} {branch:<25} {status}")
        else:
            click.echo(f"  {d.name:<20} (error)")


@git.command("checkout-all")
@click.argument("ref")
@click.option("--projects", "-p", multiple=True, help="Project directories")
@click.option("--base-dir", default=None, help="Parent directory containing projects")
async def checkout_all(ref, projects, base_dir):
    """Checkout a branch across multiple projects."""
    if base_dir:
        root = Path(base_dir).resolve()
    else:
        root = Path.cwd().parent if Path.cwd().name != "forktex" else Path.cwd()

    if projects:
        dirs = [root / p for p in projects]
    else:
        dirs = sorted(
            d for d in root.iterdir()
            if d.is_dir() and (d / ".git").exists()
        )

    for d in dirs:
        if not d.exists() or not (d / ".git").exists():
            continue
        r = await _git_checkout(str(d), ref)
        if r.is_error:
            click.echo(f"  FAIL  {d.name}: {r.content}")
        else:
            click.echo(f"  OK    {d.name}: → {ref}")
