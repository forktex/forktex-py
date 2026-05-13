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

"""FSD evaluation engine — checks a project against the standard.

Pure logic, no CLI or I/O dependencies. Takes structured inputs,
returns structured results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from forktex.fsd.models import Atom, FSDStandard
from forktex.manifest.models import FSDConfig
from forktex.fsd.profiles import resolve_applicable_atoms


class AtomStatus(str, Enum):
    """Result of evaluating a single atom."""

    SATISFIED = "satisfied"
    FAILED = "failed"
    SKIPPED = "skipped"
    OUT_OF_SCOPE = "out-of-scope"


@dataclass
class AtomResult:
    """Evaluation result for a single atom."""

    id: str
    name: str
    domain: str
    scope: str  # "service" | "project" | "organization"
    status: AtomStatus
    strategy_used: str | None = None
    detail: str = ""
    iso: list[str] = field(default_factory=list)
    required_targets: list[str] = field(default_factory=list)
    present_targets: list[str] = field(default_factory=list)
    missing_targets: list[str] = field(default_factory=list)


@dataclass
class FacetResult:
    """Evaluation result for a facet."""

    id: str
    name: str
    question: str
    satisfied: bool
    required_atoms: list[str]
    satisfied_atoms: list[str]
    missing_atoms: list[str]


@dataclass
class LevelResult:
    """Evaluation result for a level."""

    id: str
    name: str
    description: str
    achieved: bool
    required_atoms: list[str]


@dataclass
class FSDResult:
    """Complete evaluation result."""

    fsd_version: str
    project: str
    level: str
    level_name: str
    max_project_level: str  # ceiling without org evaluation
    target_level: str | None
    target_met: bool | None
    atoms: list[AtomResult]
    facets: list[FacetResult]
    levels: list[LevelResult]
    skipped: list[str]

    @property
    def satisfied_atoms(self) -> list[str]:
        return [a.id for a in self.atoms if a.status == AtomStatus.SATISFIED]

    @property
    def failed_atoms(self) -> list[str]:
        return [a.id for a in self.atoms if a.status == AtomStatus.FAILED]

    def to_evidence_dict(self) -> dict:
        """Backward-compatible evidence output format."""
        return {
            "fsd_version": self.fsd_version,
            "project": self.project,
            "level": self.level,
            "level_name": self.level_name,
            "max_project_level": self.max_project_level,
            "target_level": self.target_level,
            "target_met": self.target_met,
            "atoms": [
                {
                    "id": a.id,
                    "name": a.name,
                    "domain": a.domain,
                    "scope": a.scope,
                    "description": a.detail,
                    "status": a.status.value,
                    "strategy_used": a.strategy_used,
                    "iso": [{"ref": ref} for ref in a.iso],
                    "satisfied": a.status == AtomStatus.SATISFIED,
                    "required_targets": a.required_targets,
                    "present_required": a.present_targets,
                    "missing_required": a.missing_targets,
                }
                for a in self.atoms
            ],
            "facets": [
                {
                    "id": f.id,
                    "name": f.name,
                    "question": f.question,
                    "satisfied": f.satisfied,
                    "required_atoms": f.required_atoms,
                    "satisfied_atoms": f.satisfied_atoms,
                    "missing_atoms": f.missing_atoms,
                }
                for f in self.facets
            ],
            "levels": [
                {
                    "id": lv.id,
                    "name": lv.name,
                    "description": lv.description,
                    "achieved": lv.achieved,
                    "required_atoms": lv.required_atoms,
                }
                for lv in self.levels
            ],
            "satisfied_atoms": self.satisfied_atoms,
            "missing_atoms": self.failed_atoms,
            "skipped": self.skipped,
        }


# ── Evaluation ──────────────────────────────────────────────────────────────


def _get_domain_scope(standard: FSDStandard, domain_id: str) -> str:
    """Get the scope for a domain."""
    d = standard.domains_by_id.get(domain_id)
    return d.scope if d else "project"


def _evaluate_atom(
    atom: Atom,
    *,
    scope: str,
    make_targets: set[str],
    project_root: Path,
    skip_set: set[str],
    overrides: dict,
    applicable_atoms: set[str] | None,
    profile_disabled: set[str],
) -> AtomResult:
    """Evaluate a single atom."""
    iso_refs = [str(ref) for ref in atom.iso]
    make_tgts = atom.make_targets

    if applicable_atoms is not None and atom.id not in applicable_atoms:
        return AtomResult(
            id=atom.id,
            name=atom.name,
            domain=atom.domain,
            scope=scope,
            status=AtomStatus.OUT_OF_SCOPE,
            detail="Not applicable for active profile",
            iso=iso_refs,
            required_targets=make_tgts,
        )

    # Check if skipped
    if atom.id in skip_set or atom.domain in skip_set:
        return AtomResult(
            id=atom.id,
            name=atom.name,
            domain=atom.domain,
            scope=scope,
            status=AtomStatus.SKIPPED,
            detail="Skipped by project config",
            iso=iso_refs,
            required_targets=make_tgts,
        )

    # Org-scoped atoms are out-of-scope for project-level checks
    if scope == "organization":
        return AtomResult(
            id=atom.id,
            name=atom.name,
            domain=atom.domain,
            scope=scope,
            status=AtomStatus.OUT_OF_SCOPE,
            detail="Organization-scoped — evaluated at org level",
            iso=iso_refs,
            required_targets=make_tgts,
        )

    # Apply overrides if present
    resolve_rules = atom.resolve
    override = overrides.get(atom.id)
    if atom.id in profile_disabled or (override and override.disabled):
        return AtomResult(
            id=atom.id,
            name=atom.name,
            domain=atom.domain,
            scope=scope,
            status=AtomStatus.SKIPPED,
            detail=override.reason if override else "Disabled by active profile",
            iso=iso_refs,
            required_targets=make_tgts,
        )

    if override and override.resolve:
        resolve_rules = override.resolve
        if override.targets:
            make_tgts = override.targets + override.aliases
    elif override and (override.targets or override.aliases):
        target_names = override.targets + override.aliases
        make_tgts = target_names
        resolve_rules = [
            rule.model_copy(update={"any_of": target_names, "all_of": []})
            if rule.strategy == "make"
            else rule
            for rule in resolve_rules
        ]

    # Check each resolve rule
    for rule in resolve_rules:
        if rule.check(make_targets=make_targets, project_root=project_root):
            # Determine which strategy matched
            strategy = rule.strategy
            present = []
            if strategy == "make":
                present = [t for t in (rule.any_of + rule.all_of) if t in make_targets]
            return AtomResult(
                id=atom.id,
                name=atom.name,
                domain=atom.domain,
                scope=scope,
                status=AtomStatus.SATISFIED,
                strategy_used=strategy,
                detail=f"Satisfied via {strategy}",
                iso=iso_refs,
                required_targets=make_tgts,
                present_targets=present,
            )

    # Not satisfied
    missing = [t for t in make_tgts if t not in make_targets] if make_tgts else []
    return AtomResult(
        id=atom.id,
        name=atom.name,
        domain=atom.domain,
        scope=scope,
        status=AtomStatus.FAILED,
        detail="No resolve rule satisfied",
        iso=iso_refs,
        required_targets=make_tgts,
        missing_targets=missing,
    )


def evaluate(
    standard: FSDStandard,
    *,
    project_root: Path,
    make_targets: set[str],
    services: list[dict] | None = None,
    config: FSDConfig | None = None,
    manifest=None,
) -> FSDResult:
    """Evaluate a project against the FSD standard.

    Args:
        standard: The loaded FSD standard.
        project_root: Path to the project root.
        make_targets: All discovered Make targets (root + services).
        services: Discovered service info (for evidence output).
        config: Project-level FSD config from forktex.json.
    """
    skip_set: set[str] = set(config.skip) if config else set()
    overrides = config.atoms if config else {}
    target_level = config.target_level if config else None
    applicable_atoms, profile_disabled = (
        resolve_applicable_atoms(manifest, package_manifest=None)
        if manifest
        else (None, set())
    )

    # Evaluate atoms
    atom_results: list[AtomResult] = []
    atom_status: dict[str, AtomStatus] = {}

    for atom in standard.atoms:
        scope = _get_domain_scope(standard, atom.domain)
        result = _evaluate_atom(
            atom,
            scope=scope,
            make_targets=make_targets,
            project_root=project_root,
            skip_set=skip_set,
            overrides=overrides,
            applicable_atoms=applicable_atoms,
            profile_disabled=profile_disabled,
        )
        atom_results.append(result)
        atom_status[atom.id] = result.status

    # Evaluate facets
    facet_results: list[FacetResult] = []
    facet_satisfied: dict[str, bool] = {}

    for facet in standard.facets:
        required_atom_ids = facet.resolve_required_atoms(standard.facets_by_id)
        sat = []
        missing = []
        for aid in required_atom_ids:
            status = atom_status.get(aid, AtomStatus.FAILED)
            if status in (
                AtomStatus.SATISFIED,
                AtomStatus.SKIPPED,
                AtomStatus.OUT_OF_SCOPE,
            ):
                sat.append(aid)
            else:
                missing.append(aid)

        ok = len(missing) == 0
        facet_satisfied[facet.id] = ok
        facet_results.append(
            FacetResult(
                id=facet.id,
                name=facet.name,
                question=facet.question,
                satisfied=ok,
                required_atoms=required_atom_ids,
                satisfied_atoms=sat,
                missing_atoms=missing,
            )
        )

    # Determine level
    achieved_level = standard.levels[0] if standard.levels else None
    max_project_level = "L4"

    level_results: list[LevelResult] = []
    for level in standard.levels:
        required = set()
        for fid in level.facets:
            f = standard.facets_by_id.get(fid)
            if f:
                required.update(f.resolve_required_atoms(standard.facets_by_id))

        ok = all(
            atom_status.get(aid, AtomStatus.FAILED)
            in (
                AtomStatus.SATISFIED,
                AtomStatus.SKIPPED,
                AtomStatus.OUT_OF_SCOPE,
            )
            for aid in required
        )

        if ok:
            achieved_level = level

        level_results.append(
            LevelResult(
                id=level.id,
                name=level.name,
                description=level.description,
                achieved=ok,
                required_atoms=sorted(required),
            )
        )

    level_id = achieved_level.id if achieved_level else "L0"
    level_name = achieved_level.name if achieved_level else "Bootstrap"

    # Target check
    target_met = None
    if target_level:
        target_met = level_id >= target_level

    return FSDResult(
        fsd_version=standard.version,
        project=project_root.name,
        level=level_id,
        level_name=level_name,
        max_project_level=max_project_level,
        target_level=target_level,
        target_met=target_met,
        atoms=atom_results,
        facets=facet_results,
        levels=level_results,
        skipped=sorted(skip_set),
    )
