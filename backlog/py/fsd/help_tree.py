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

"""Typed help tree for FSD atoms and generated Make targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from forktex.fsd.models import Atom, FSDStandard
from forktex.fsd.profiles import resolve_applicable_atoms
from forktex.fsd.variants import parse_atom_key
from forktex.manifest.models import AtomOverride, ForktexManifest


HelpKind = Literal["atom", "custom", "alias", "secondary", "suggested"]


@dataclass(frozen=True)
class HelpEntry:
    """One visible help row backed by the typed atom tree."""

    target: str
    description: str
    base_id: str
    kind: HelpKind
    make_invocation: str | None = None
    cli_invocation: str | None = None
    variant_key: str | None = None
    runnable: bool = True


@dataclass(frozen=True)
class HelpTree:
    """In-memory view of all currently known atom unfoldings."""

    project_name: str
    services: tuple[str, ...]
    envs: tuple[str, ...]
    entries: tuple[HelpEntry, ...]

    def for_atom(self, atom_id: str) -> tuple[HelpEntry, ...]:
        return tuple(entry for entry in self.entries if entry.base_id == atom_id)

    @property
    def root_entries(self) -> tuple[HelpEntry, ...]:
        return tuple(entry for entry in self.entries if entry.kind != "suggested")


def project_axes(manifest: ForktexManifest | None) -> tuple[set[str], set[str]]:
    """Extract canonical service/env axis values from a project manifest."""
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
                env.get("name") if isinstance(env, dict) else getattr(env, "name", None)
            )
            if name:
                envs.add(name)

    return services, envs


def build_help_tree(
    standard: FSDStandard,
    manifest: ForktexManifest,
    *,
    cli_atoms: Iterable[str] | None = None,
    include_suggestions: bool = True,
) -> HelpTree:
    """Build the shared help tree used by Make and atom CLI help."""
    services, envs = project_axes(manifest)
    cli_atom_set = set(cli_atoms or ())
    entries: list[HelpEntry] = []
    seen_targets: set[str] = set()

    for atom in _applicable_atoms(standard, manifest):
        override = _get_override(manifest, atom.id)
        target, _aliases = _target_names(atom, override, services=services, envs=envs)
        if target in seen_targets:
            continue
        seen_targets.add(target)
        entries.append(
            _entry_for_atom(
                atom,
                target=target,
                override=override,
                kind="atom",
                cli_available=atom.id in cli_atom_set,
            )
        )

    for atom_id, override in _custom_atoms(manifest, standard):
        target, _aliases = _target_names(
            Atom(id=atom_id, name=atom_id, description=override.description or atom_id),
            override,
            services=services,
            envs=envs,
        )
        if target in seen_targets:
            continue
        seen_targets.add(target)
        parsed = parse_atom_key(atom_id, services=services, envs=envs)
        entries.append(
            HelpEntry(
                target=target,
                make_invocation=f"make {target}",
                cli_invocation=None,
                description=override.description or f"Custom atom: {atom_id}",
                base_id=parsed.base_id,
                kind="custom",
                variant_key=atom_id,
            )
        )

    for entry in _secondary_entries(manifest, seen_targets):
        seen_targets.add(entry.target)
        entries.append(entry)

    for alias, invocations in standard.aliases.items():
        target_names = [
            parse_atom_key(invocation, services=services, envs=envs).make_target
            for invocation in invocations
        ]
        if alias in seen_targets or not all(
            target in seen_targets for target in target_names
        ):
            continue
        seen_targets.add(alias)
        entries.append(
            HelpEntry(
                target=alias,
                make_invocation=f"make {alias}",
                cli_invocation=None,
                description="chord (" + " + ".join(invocations) + ")",
                base_id=alias,
                kind="alias",
            )
        )

    if include_suggestions:
        entries.extend(
            _suggested_entries(
                standard,
                services=services,
                envs=envs,
                seen_targets=seen_targets,
                cli_atoms=cli_atom_set,
            )
        )

    entries.sort(key=lambda e: (_kind_order(e.kind), e.base_id, e.target))
    return HelpTree(
        project_name=manifest.project_name or manifest.name or "project",
        services=tuple(sorted(services)),
        envs=tuple(sorted(envs)),
        entries=tuple(entries),
    )


def render_help_text(tree: HelpTree, *, atom_id: str | None = None) -> str:
    """Render deterministic plain help text."""
    entries = tree.for_atom(atom_id) if atom_id else tree.root_entries
    title = f"{tree.project_name} help"
    if atom_id:
        title += f": {atom_id}"
    if not entries:
        return title + "\n\n  (no entries)"

    rows = [
        (
            entry.target,
            _surface(entry),
            _kind_label(entry),
            entry.description,
        )
        for entry in entries
    ]
    return _plain_table(title, ("target", "surface", "kind", "description"), rows)


def render_help_rich(tree: HelpTree, *, atom_id: str | None = None) -> bool:
    """Render a Rich table when Rich is importable; return whether it worked."""
    try:
        from rich.console import Console
        from rich.table import Table
    except Exception:
        return False

    entries = tree.for_atom(atom_id) if atom_id else tree.root_entries
    title = (
        f"{tree.project_name} help"
        if not atom_id
        else f"{tree.project_name}: {atom_id}"
    )
    table = Table(title=title, show_lines=False)
    table.add_column("target", style="cyan", no_wrap=True)
    table.add_column("surface", style="green")
    table.add_column("kind", style="magenta", no_wrap=True)
    table.add_column("description")
    for entry in entries:
        table.add_row(
            entry.target, _surface(entry), _kind_label(entry), entry.description
        )
    Console().print(table)
    return True


def _applicable_atoms(standard: FSDStandard, manifest: ForktexManifest) -> list[Atom]:
    applicable, disabled = resolve_applicable_atoms(manifest)
    config = manifest.fsd
    if config:
        disabled |= {
            atom_id for atom_id, override in config.atoms.items() if override.disabled
        }
    atoms: list[Atom] = []
    for atom in standard.atoms:
        override = _get_override(manifest, atom.id)
        explicitly_enabled = bool(
            override
            and not override.disabled
            and (
                override.commands
                or override.targets
                or override.aliases
                or override.description
            )
        )
        if (
            applicable is not None
            and atom.id not in applicable
            and not explicitly_enabled
        ):
            continue
        if atom.id in disabled and not explicitly_enabled:
            continue
        if not atom.make_targets:
            continue
        atoms.append(atom)
    return atoms


def _custom_atoms(
    manifest: ForktexManifest, standard: FSDStandard
) -> list[tuple[str, AtomOverride]]:
    config = manifest.fsd
    if not config:
        return []
    standard_ids = set(standard.atoms_by_id)
    return [
        (atom_id, override)
        for atom_id, override in config.atoms.items()
        if atom_id not in standard_ids and override.commands
    ]


def _get_override(manifest: ForktexManifest, atom_id: str) -> AtomOverride | None:
    if not manifest.fsd:
        return None
    return manifest.fsd.atoms.get(atom_id)


def _target_names(
    atom: Atom,
    override: AtomOverride | None,
    *,
    services: set[str],
    envs: set[str],
) -> tuple[str, list[str]]:
    if override and override.targets:
        return override.targets[0], list(dict.fromkeys(override.aliases))
    primary = (atom.make_targets or [atom.id])[0]
    if "@" in primary:
        primary = parse_atom_key(primary, services=services, envs=envs).make_target
    return primary, list(override.aliases if override else [])


def _entry_for_atom(
    atom: Atom,
    *,
    target: str,
    override: AtomOverride | None,
    kind: HelpKind,
    cli_available: bool,
) -> HelpEntry:
    description = (
        override.description if override and override.description else atom.description
    )
    return HelpEntry(
        target=target,
        make_invocation=f"make {target}",
        cli_invocation=f"forktex {atom.id}" if cli_available else None,
        description=description,
        base_id=atom.id,
        kind=kind,
        variant_key=atom.id,
        runnable=True,
    )


def _secondary_entries(
    manifest: ForktexManifest, existing_targets: set[str]
) -> tuple[HelpEntry, ...]:
    has_root_python = any(
        pkg.path == "." and pkg.publishable and pkg.language == "python"
        for pkg in manifest.packages
    )
    subpaths = [
        pkg.path
        for pkg in manifest.packages
        if pkg.path != "." and pkg.publishable and pkg.language == "python"
    ]
    has_workspace_runtime = has_root_python or bool(subpaths)
    if not has_workspace_runtime:
        return ()

    candidates = [
        ("format-check", "Check formatting without rewriting files"),
        ("lint-fix", "Lint and auto-fix where possible"),
    ]
    if has_root_python:
        candidates.extend(
            [
                ("test-cov", "Run tests with coverage"),
                ("deps-lock", "Lock dependencies"),
                (
                    "install-global",
                    "Install the latest local forktex CLI globally in editable mode",
                ),
            ]
        )
    return tuple(
        HelpEntry(
            target=target,
            make_invocation=f"make {target}",
            cli_invocation=None,
            description=description,
            base_id=target,
            kind="secondary",
        )
        for target, description in candidates
        if target not in existing_targets
    )


def _suggested_entries(
    standard: FSDStandard,
    *,
    services: set[str],
    envs: set[str],
    seen_targets: set[str],
    cli_atoms: set[str],
) -> tuple[HelpEntry, ...]:
    entries: list[HelpEntry] = []
    for atom in standard.atoms:
        for variant in atom.common_variants:
            parsed = parse_atom_key(variant, services=services, envs=envs)
            target = parsed.make_target
            if target in seen_targets:
                continue
            entries.append(
                HelpEntry(
                    target=target,
                    make_invocation=f"make {target}",
                    cli_invocation=_cli_variant(atom.id, parsed)
                    if atom.id in cli_atoms
                    else None,
                    description=atom.description,
                    base_id=atom.id,
                    kind="suggested",
                    variant_key=variant,
                    runnable=False,
                )
            )
    return tuple(entries)


def _cli_variant(atom_id: str, parsed) -> str:
    parts = [f"forktex {atom_id}"]
    if parsed.service:
        parts.append(f"--service {parsed.service}")
    if parsed.env:
        parts.append(f"--env {parsed.env}")
    for item in parsed.custom:
        parts.append(f"--scope {item}")
    return " ".join(parts)


def _surface(entry: HelpEntry) -> str:
    values = [value for value in (entry.make_invocation, entry.cli_invocation) if value]
    if not values:
        return "-"
    if not entry.runnable:
        return "suggest: " + " / ".join(values)
    return " / ".join(values)


def _kind_label(entry: HelpEntry) -> str:
    if entry.kind == "suggested":
        return "suggested"
    return entry.kind


def _plain_table(
    title: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]
) -> str:
    widths = [
        max(len(headers[idx]), *(len(row[idx]) for row in rows))
        for idx in range(len(headers))
    ]
    lines = [title, ""]
    lines.append(
        "  "
        + "  ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    )
    lines.append("  " + "  ".join("-" * width for width in widths))
    for row in rows:
        lines.append(
            "  " + "  ".join(value.ljust(widths[idx]) for idx, value in enumerate(row))
        )
    return "\n".join(lines)


def _kind_order(kind: HelpKind) -> int:
    return {
        "atom": 0,
        "custom": 1,
        "alias": 2,
        "secondary": 3,
        "suggested": 4,
    }[kind]


__all__ = [
    "HelpEntry",
    "HelpTree",
    "build_help_tree",
    "project_axes",
    "render_help_rich",
    "render_help_text",
]
