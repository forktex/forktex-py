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

"""Catalog-driven atom dispatch.

Every FSD atom in ``src/forktex/data/fsd/standard.json`` becomes a
top-level ``forktex <atom>`` Click command. Variants surface as
``--service``, ``--env``, and repeatable ``--scope`` flags; resolution
goes through ``forktex.fsd.variants.parse_atom_key`` so the variant
syntax matches what the Makefile generator emits.

Execution is a shell-out to ``make <target>`` from the resolved
project root. Output streams in real time (no capture); exit code
propagates.

Collisions with existing top-level Click commands are handled in
``register_atom_commands``:

- A ``@click.command`` (e.g. ``clean``) wins outright; the atom is
  reachable only via ``make <atom>`` (documented in the README).
- A ``@click.group`` registered with ``invoke_without_command=True``
  (e.g. ``manual``) keeps its subcommands but routes the no-subverb
  invocation to the atom dispatcher via the group's body.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import asyncclick as click

from forktex.fsd.models import Atom, FSDStandard
from forktex.fsd.variants import ParsedAtom, parse_atom_key


class AtomDispatchError(click.ClickException):
    """Raised when an atom invocation can't be routed to a Make target."""


# ── Public entry points ───────────────────────────────────────────────────


def dispatch_atom(
    atom_id: str,
    *,
    project_root: Path,
    service: str | None = None,
    env: str | None = None,
    scope: tuple[str, ...] = (),
    services: Iterable[str] | None = None,
    envs: Iterable[str] | None = None,
) -> int:
    """Resolve an atom + variant flags to a Make target and run it.

    Returns the subprocess exit code so callers can ``ctx.exit(rc)``.
    Raises :class:`AtomDispatchError` if Make isn't installed.
    """
    if shutil.which("make") is None:
        raise AtomDispatchError(
            "GNU Make not found on PATH. Install it (apt install make / "
            "brew install make) — `forktex <atom>` shells out to `make`."
        )

    parsed = _build_parsed(
        atom_id,
        service=service,
        env=env,
        scope=scope,
        services=services,
        envs=envs,
    )
    target = parsed.make_target
    cmd = ["make", target]
    proc = subprocess.run(cmd, cwd=project_root)
    return proc.returncode


def register_atom_commands(
    cli: click.Group, *, standard: FSDStandard, manifest=None
) -> list[str]:
    """Wire one Click command per FSD atom onto *cli*.

    Returns the list of atom IDs that were registered as new top-level
    commands. Atoms whose IDs collide with an existing
    non-``invoke_without_command`` command are skipped (the existing
    command keeps its surface; the atom is invoked via ``make <id>``).

    Atoms whose IDs collide with a Click group declared with
    ``invoke_without_command=True`` are *not* registered separately —
    the group's body owns the no-subverb fallback (see
    ``forktex.agent.manual.cli.manual``).
    """
    services, envs = _project_axes(manifest)
    registered: list[str] = []

    existing = set(cli.commands.keys())
    for atom in standard.atoms:
        if atom.id in existing:
            existing_cmd = cli.commands[atom.id]
            if (
                isinstance(existing_cmd, click.Group)
                and existing_cmd.invoke_without_command
            ):
                # Group will handle atom dispatch in its body.
                continue
            # Plain command — it owns the name; atom is reachable via make only.
            continue

        cmd = _build_atom_command(atom, services=services, envs=envs)
        cli.add_command(cmd, name=atom.id)
        registered.append(atom.id)

    return registered


# ── Private helpers ───────────────────────────────────────────────────────


def _build_parsed(
    atom_id: str,
    *,
    service: str | None,
    env: str | None,
    scope: tuple[str, ...],
    services: Iterable[str] | None,
    envs: Iterable[str] | None,
) -> ParsedAtom:
    """Build a ``ParsedAtom`` from CLI flags.

    Skips the variant parser when no flags are passed (bare atom).
    Uses the parser when at least one flag is given so axis validation
    runs through the same code path as keys read from forktex.json.
    """
    if not service and not env and not scope:
        return ParsedAtom(base_id=atom_id)

    # Construct an equivalent variant key and let the parser resolve it.
    parts = [atom_id]
    if service:
        parts.append(service)
    if env:
        parts.append(env)
    parts.extend(scope)
    key = "@".join(parts)
    return parse_atom_key(
        key,
        services=services or set(),
        envs=envs or set(),
    )


def _project_axes(manifest) -> tuple[set[str], set[str]]:
    """Extract recognised ``services`` and ``envs`` from the manifest.

    Mirrors ``forktex.fsd.makefile._project_axes`` but kept local to
    avoid importing the generator (which pulls a much larger graph).
    """
    services: set[str] = set()
    envs: set[str] = set()
    if manifest is None:
        return services, envs
    for pkg in getattr(manifest, "packages", []) or []:
        name = getattr(pkg, "name", None)
        if name:
            services.add(name)
        path = getattr(pkg, "path", None)
        if path and path != ".":
            services.add(path)
    cloud = getattr(manifest, "cloud", None)
    if cloud is not None:
        for env in getattr(cloud, "environments", []) or []:
            name = (
                getattr(env, "name", None)
                if not isinstance(env, dict)
                else env.get("name")
            )
            if name:
                envs.add(name)
    return services, envs


def _build_atom_command(
    atom: Atom, *, services: set[str], envs: set[str]
) -> click.Command:
    """Construct a single Click command for an atom."""
    help_lines: list[str] = []
    if atom.description:
        help_lines.append(atom.description)
    if atom.common_variants:
        help_lines.append("")
        help_lines.append("Common variants: " + ", ".join(atom.common_variants))
    short_help = atom.description.split(".")[0] if atom.description else atom.id
    help_text = "\n".join(help_lines) or atom.id

    @click.command(name=atom.id, short_help=short_help, help=help_text)
    @click.option(
        "--service",
        "service",
        default=None,
        help="Service axis (matches a package name in forktex.json).",
    )
    @click.option(
        "--env",
        "env",
        default=None,
        help="Env axis (matches a cloud.environments[].name in forktex.json).",
    )
    @click.option(
        "--scope",
        "scope",
        multiple=True,
        help="Free-form qualifier (repeatable; appended in order).",
    )
    async def _cmd(service, env, scope):
        from forktex.core.paths import find_project_root

        cwd = Path.cwd()
        project_root = find_project_root(cwd)
        if project_root is None:
            raise AtomDispatchError(
                f"no forktex.json found at or above {cwd}.\n"
                "Run from a project directory or `cd` into one."
            )
        rc = dispatch_atom(
            atom.id,
            project_root=project_root,
            service=service,
            env=env,
            scope=tuple(scope),
            services=services,
            envs=envs,
        )
        sys.exit(rc)

    return _cmd


__all__ = ["AtomDispatchError", "dispatch_atom", "register_atom_commands"]
