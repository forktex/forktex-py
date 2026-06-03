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

"""CLI commands for Makefile generation and sync from FSD atoms."""

from __future__ import annotations

from pathlib import Path

import asyncclick as click

from forktex.fsd.loader import (
    ensure_fsd_supported,
    ensure_manifest_supported,
    load_standard,
)
from forktex.fsd.makefile import generate_makefiles
from forktex.manifest.models import ForktexManifest


def _write_makefiles(generated, *, overwrite: bool) -> list[Path]:
    written: list[Path] = []
    for item in generated:
        path = item.unit_path / "Makefile"
        if path.exists() and not overwrite:
            raise click.ClickException(f"Makefile already exists: {path}")
        path.write_text(item.content)
        written.append(path)
    return written


@click.group("makefile")
@click.pass_context
async def makefile_group(ctx):
    """Generate or sync Makefiles from FSD atoms."""
    ctx.ensure_object(dict)


@makefile_group.command("generate")
@click.option(
    "--package", default=None, help="Generate for one package path or package name"
)
@click.option(
    "--all-packages", is_flag=True, help="Also generate nested package Makefiles"
)
@click.option(
    "--stdout",
    "to_stdout",
    is_flag=True,
    help="Print generated content instead of writing files",
)
@click.option("--force", is_flag=True, help="Overwrite existing Makefiles")
@click.pass_context
async def generate_cmd(ctx, package, all_packages, to_stdout, force):
    """Generate Makefiles from the active FSD standard."""
    project_root: Path = ctx.obj["project_root"]
    manifest = ForktexManifest.load(project_root / "forktex.json")
    ensure_manifest_supported(manifest)
    standard = load_standard()
    ensure_fsd_supported(standard, manifest.fsd)
    generated = generate_makefiles(
        project_root, standard, manifest, package=package, all_packages=all_packages
    )

    if to_stdout:
        for item in generated:
            click.echo(f"# --- {item.unit_name} ({item.unit_path}) ---")
            click.echo(item.content)
        return

    written = _write_makefiles(generated, overwrite=force)
    for path in written:
        click.echo(f"Wrote {path}")


@makefile_group.command("sync")
@click.option("--package", default=None, help="Sync one package path or package name")
@click.option("--all-packages", is_flag=True, help="Also sync nested package Makefiles")
@click.option(
    "--check",
    "check_only",
    is_flag=True,
    help="Verify Makefiles match their forktex.json source without writing; "
    "exit non-zero on drift (CI drift gate — forbids hand-patches)",
)
@click.pass_context
async def sync_cmd(ctx, package, all_packages, check_only):
    """Synchronize Makefiles from the active FSD standard.

    With ``--check`` the Makefiles are regenerated in memory and compared to
    what is on disk; nothing is written and a unified diff + non-zero exit are
    produced on any drift. This is the gate that keeps Makefiles a pure
    projection of ``forktex.json`` — a hand-edited Makefile can never pass CI.
    """
    import difflib

    project_root: Path = ctx.obj["project_root"]
    manifest = ForktexManifest.load(project_root / "forktex.json")
    ensure_manifest_supported(manifest)
    standard = load_standard()
    ensure_fsd_supported(standard, manifest.fsd)
    generated = generate_makefiles(
        project_root, standard, manifest, package=package, all_packages=all_packages
    )

    if check_only:
        drifted: list[Path] = []
        for item in generated:
            path = item.unit_path / "Makefile"
            current = path.read_text() if path.exists() else ""
            if current != item.content:
                drifted.append(path)
                for line in difflib.unified_diff(
                    current.splitlines(),
                    item.content.splitlines(),
                    fromfile=f"{path} (on disk)",
                    tofile=f"{path} (generated from forktex.json)",
                    lineterm="",
                ):
                    click.echo(line)
        if drifted:
            names = ", ".join(str(p) for p in drifted)
            raise click.ClickException(
                f"{len(drifted)} Makefile(s) drift from forktex.json ({names}). "
                "Makefiles are generated — edit forktex.json and run "
                "'forktex fsd makefile sync', do not hand-patch the Makefile."
            )
        click.echo(
            f"makefile-check: {len(generated)} Makefile(s) in sync with forktex.json"
        )
        return

    written = _write_makefiles(generated, overwrite=True)
    for path in written:
        click.echo(f"Synced {path}")
