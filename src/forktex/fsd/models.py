"""FSD domain models.

This module is the canonical home for FSD-related object models.

It currently contains:
- the existing standard.json-backed model used by the evaluator
- the new portable v1 source-of-truth objects

Compatibility re-exports may remain under ``forktex.models`` while the
package structure migrates toward domain-oriented ownership.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, computed_field

from forktex.models.base import ForkTexModel, Identifiable, Tagged, Versioned


class ISORef(ForkTexModel):
    """Reference to an ISO control clause."""

    standard: str
    clause: str
    control: str = ""

    @classmethod
    def from_string(cls, s: str) -> "ISORef":
        parts = s.split(":", 1)
        return cls(standard=parts[0], clause=parts[1] if len(parts) > 1 else "")

    def __str__(self) -> str:
        return f"{self.standard}:{self.clause}"


class ResolveRule(ForkTexModel):
    """One way to check if an atom is satisfied."""

    strategy: Literal["make", "path", "file-content", "field"]
    any_of: list[str] = []
    all_of: list[str] = []
    file: str | None = None
    path: str | None = None

    def check(
        self,
        *,
        make_targets: set[str] | None = None,
        project_root: Path | None = None,
        docs_root: Path | None = None,
    ) -> bool:
        _targets = make_targets or set()
        _root = project_root or docs_root

        if self.strategy == "make":
            if self.any_of:
                return any(t in _targets for t in self.any_of)
            if self.all_of:
                return all(t in _targets for t in self.all_of)
            return False

        if self.strategy == "path" and _root:
            if self.all_of:
                return all((_root / p).exists() for p in self.all_of)
            if self.any_of:
                return any((_root / p).exists() for p in self.any_of)
            return False

        if self.strategy == "field" and self.file and _root:
            file_path = _root / self.file
            if not file_path.exists():
                return False
            try:
                data = json.loads(file_path.read_text())
                for part in (self.path or "").split("."):
                    data = data.get(part) if isinstance(data, dict) else None
                return data is not None
            except (json.JSONDecodeError, AttributeError):
                return False

        if self.strategy == "file-content" and _root:
            targets = self.all_of or self.any_of
            if not targets:
                return False
            for file_rel in targets:
                fp = _root / file_rel
                if not fp.is_file():
                    if self.all_of:
                        return False
                    continue
                return True
            return False

        return False


class Domain(Identifiable):
    """Legacy FSD grouping backed by the current standard.json."""

    track: str = ""
    scope: Literal["service", "project", "organization"]


class Atom(Identifiable):
    """A single verifiable capability in the current FSD standard."""

    domain: str = ""
    resolve: list[ResolveRule] = []
    iso: list[ISORef] = []
    evidence: str = ""

    @computed_field
    @property
    def make_targets(self) -> list[str]:
        targets = []
        for rule in self.resolve:
            if rule.strategy == "make":
                targets.extend(rule.any_of)
                targets.extend(rule.all_of)
        return targets

    def check(
        self,
        *,
        make_targets: set[str] | None = None,
        project_root: Path | None = None,
        docs_root: Path | None = None,
    ) -> bool:
        if not self.resolve:
            return False
        return any(
            rule.check(make_targets=make_targets, project_root=project_root, docs_root=docs_root)
            for rule in self.resolve
        )


class FacetAtomRef(ForkTexModel):
    """Reference to an atom within a legacy FSD facet."""

    ref: str
    required: bool = True


class Facet(Identifiable):
    """Legacy middle layer used by the current standard.json."""

    domain: str = ""
    question: str = ""
    atoms: list[FacetAtomRef] = []
    composes_from: list[str] = Field(default=[], alias="composesFrom")

    def resolve_required_atoms(self, facets_by_id: dict[str, "Facet"]) -> list[str]:
        result = [ref.ref for ref in self.atoms if ref.required]
        for sub_id in self.composes_from:
            sub = facets_by_id.get(sub_id)
            if sub:
                result.extend(sub.resolve_required_atoms(facets_by_id))
        return result


class Level(Identifiable):
    """Legacy maturity threshold backed by the current standard.json."""

    facets: list[str] = []


class FSDStandard(Versioned):
    """Current standard.json-backed FSD model."""

    domains: list[Domain] = []
    atoms: list[Atom] = []
    facets: list[Facet] = []
    levels: list[Level] = []

    @computed_field
    @property
    def atoms_by_id(self) -> dict[str, Atom]:
        return {a.id: a for a in self.atoms}

    @computed_field
    @property
    def facets_by_id(self) -> dict[str, Facet]:
        return {f.id: f for f in self.facets}

    @computed_field
    @property
    def domains_by_id(self) -> dict[str, Domain]:
        return {d.id: d for d in self.domains}

    def determine_level(self, *, make_targets: set[str] = set(), docs_root: Path | None = None) -> Level:
        achieved = self.levels[0] if self.levels else Level(id="L0", name="Bootstrap")
        for level in self.levels:
            if self._check_level(level, make_targets=make_targets, docs_root=docs_root):
                achieved = level
        return achieved

    def _check_level(self, level: Level, **kwargs) -> bool:
        for fid in level.facets:
            facet = self.facets_by_id.get(fid)
            if not facet:
                return False
            required_atoms = facet.resolve_required_atoms(self.facets_by_id)
            for aid in required_atoms:
                atom = self.atoms_by_id.get(aid)
                if not atom or not atom.check(**kwargs):
                    return False
        return True

    @classmethod
    def from_json(cls, path: Path) -> "FSDStandard":
        raw = json.loads(path.read_text())
        raw["domains"] = [d for d in raw.get("domains", []) if not d.get("_comment")]
        raw["atoms"] = [a for a in raw.get("atoms", []) if not a.get("_comment")]
        raw["facets"] = [f for f in raw.get("facets", []) if not f.get("_comment")]
        for atom in raw["atoms"]:
            atom["iso"] = [ISORef.from_string(s) if isinstance(s, str) else s for s in atom.get("iso", [])]
        return cls.model_validate(raw)


class FSDAtom(Identifiable, Tagged):
    """Smallest semantic capability in the portable FSD standard."""


class FSDDomain(Identifiable):
    """Technical grouping layer between atoms and levels."""

    question: str = ""
    atoms: list[str] = []


class FSDLevel(Identifiable):
    """Maturity threshold expressed as required domains."""

    domains: list[str] = []


class FSDStandardV1(Versioned):
    """Portable software-generic FSD source of truth."""

    kind: Literal["FSDStandard"] = "FSDStandard"
    atoms: list[FSDAtom] = []
    domains: list[FSDDomain] = []
    levels: list[FSDLevel] = []

    @computed_field
    @property
    def atoms_by_id(self) -> dict[str, FSDAtom]:
        return {atom.id: atom for atom in self.atoms}

    @computed_field
    @property
    def domains_by_id(self) -> dict[str, FSDDomain]:
        return {domain.id: domain for domain in self.domains}

    @computed_field
    @property
    def levels_by_id(self) -> dict[str, FSDLevel]:
        return {level.id: level for level in self.levels}


class FSDProfileAtomPolicy(ForkTexModel):
    """Applicability policy for one atom within a reusable profile."""

    required: bool | None = None
    disabled: bool = False
    reason: str = ""
    adapters: list[str] = []


class FSDProfile(Identifiable, Versioned):
    """Reusable applicability profile for a software kind."""

    kind: Literal["FSDProfile"] = "FSDProfile"
    requires: list[str] = []
    optional: list[str] = []
    disables: list[str] = []
    atoms: dict[str, FSDProfileAtomPolicy] = {}
    target_level: str | None = Field(None, alias="targetLevel")


class FSDProjectAtomOverride(ForkTexModel):
    """Project-local delta for how one atom applies or resolves."""

    disabled: bool = False
    reason: str = ""
    resolve: list[ResolveRule] = []


class FSDProjectConfig(ForkTexModel):
    """Project-local FSD usage declared in forktex.json."""

    version: str | None = Field(
        None,
        alias="version",
        validation_alias=AliasChoices("version", "standardVersion"),
    )
    profiles: list[str] = []
    target_level: str | None = Field(None, alias="targetLevel")
    atoms: dict[str, FSDProjectAtomOverride] = {}
