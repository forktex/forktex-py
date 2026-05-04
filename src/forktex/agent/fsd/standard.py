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

"""FSD Standard definitions — atoms, facets, levels, domains, and resolution.

Source of truth for the ForkTex Standard for Delivery.

FSD is a composable quality contract for the FORKTEX ecosystem.
FORKTEX is a software factory that manages itself through its own products:
Cloud deploys platforms, Network handles communications, Intelligence provides AI.
FSD governs this spiral — defining what a well-functioning piece looks like.

Architecture:
  standard.json   Machine-readable standard (domains, atoms, facets, levels)
  standard.py     Resolution engine (this module)
  check.py        CLI: verify projects/org against the standard

Domains map atoms to organizational concerns (and docs/ tracks):
  code         → engineering/      Source code correctness, style, safety
  data         → engineering/      Persistence, migrations, seeding
  infra        → engineering/      Local env, build, publish
  ops          → platforms/        Deploy, backup, rollback, monitor
  governance   → company/          Policies, registers, org structure
  process      → processes/        Procedures, workflows
  compliance   → compliance/       ISO, legal, audit evidence
  supply-chain → third-parties/    Supplier management

Resolution strategies (pluggable — an atom can use any combination):
  make         — At least one Make target exists
  path         — File or directory exists relative to docs/
  field        — JSON/YAML field is non-null in a manifest
  file-content — File contains required markers (future)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


FSD_VERSION = "1.0.0"  # Compatibility version. Bundled standard.json must match.


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class ISOMapping:
    standard: str  # "27001" or "9001"
    clause: str  # e.g., "A.8.28"
    control: str  # human-readable name


@dataclass
class ResolveRule:
    """One way to check if an atom is satisfied.

    strategy: "make" | "path" | "file-content" | "field"
    any_of:   At least one must match (OR). Used for make targets and path alternatives.
    all_of:   All must match (AND). Used for required file sets.
    file:     Target file (for "field" strategy).
    path:     JSON path within file (for "field" strategy).
    """

    strategy: Literal["make", "path", "file-content", "field"]
    any_of: list[str] = field(default_factory=list)
    all_of: list[str] = field(default_factory=list)
    file: str | None = None
    path: str | None = None


@dataclass
class Domain:
    """Organizational concern area. Maps to a docs/ track."""

    id: str
    name: str
    description: str
    track: str  # docs/ subdirectory
    scope: Literal["service", "project", "organization"]


@dataclass
class Atom:
    """A single FSD capability.

    Atoms are abstract. Resolution is via ResolveRules — an atom says
    "code is formatted" not "run ruff". The resolve list defines HOW
    to check satisfaction; each rule is a strategy (make, path, field).

    required_targets / optional_targets are derived from make-strategy
    rules for tools that only understand Make targets (e.g., check.py).
    """

    id: str
    name: str
    description: str
    domain: str = ""
    resolve: list[ResolveRule] = field(default_factory=list)
    iso: list[ISOMapping] = field(default_factory=list)
    evidence: str = ""

    # Derived from make-strategy rules for Make-only tools
    required_targets: list[str] = field(default_factory=list)
    optional_targets: list[str] = field(default_factory=list)

    @property
    def all_targets(self) -> list[str]:
        return self.required_targets + self.optional_targets

    @property
    def make_targets(self) -> list[str]:
        """All Make targets from resolve rules (v2)."""
        targets = []
        for rule in self.resolve:
            if rule.strategy == "make":
                targets.extend(rule.any_of)
                targets.extend(rule.all_of)
        return targets or self.required_targets


@dataclass
class FacetAtomRef:
    """Reference to an atom within a facet."""

    atom_id: str
    required: bool = True  # True = gates the facet, False = tracked only


@dataclass
class Facet:
    id: str
    name: str
    question: str
    domain: str = ""
    atom_refs: list[FacetAtomRef] = field(default_factory=list)
    composes_from: list[str] = field(default_factory=list)


@dataclass
class Level:
    id: str
    name: str
    description: str
    facet_ids: list[str]


# ── Atoms ────────────────────────────────────────────────────────────────────
# Ordered by lifecycle phase. Required targets reflect what network/survey
# actually implement today. Optional targets are aspirational or variant.

ATOMS: list[Atom] = [
    # ── Dependencies ──
    Atom(
        "deps",
        "Dependencies",
        "Install project dependencies",
        required_targets=["deps"],
        optional_targets=["deps-lock"],
        iso=[
            ISOMapping("27001", "A.8.9", "Configuration management"),
            ISOMapping("9001", "7.1", "Resources"),
        ],
    ),
    # ── Code Quality ──
    Atom(
        "format",
        "Format",
        "Auto-format source code",
        required_targets=["format"],
        optional_targets=["format-check"],
        iso=[ISOMapping("9001", "8.3.4", "Design and development controls")],
    ),
    Atom(
        "lint",
        "Lint",
        "Static analysis and code quality checks",
        required_targets=["lint"],
        optional_targets=["lint-fix"],
        iso=[
            ISOMapping("27001", "A.8.26", "Application security requirements"),
            ISOMapping("27001", "A.8.28", "Secure coding"),
        ],
    ),
    Atom(
        "typecheck",
        "Type Check",
        "Static type verification",
        required_targets=["typecheck"],
        iso=[ISOMapping("27001", "A.8.27", "Secure system architecture")],
    ),
    # ── Testing ──
    Atom(
        "test",
        "Test",
        "Run test suite (real infrastructure, not mocks)",
        required_targets=["test"],
        optional_targets=["test-cov"],
        iso=[
            ISOMapping("27001", "A.8.29", "Security testing"),
            ISOMapping("9001", "8.6", "Release of products"),
            ISOMapping("9001", "9.1.1", "Monitoring and measurement"),
        ],
    ),
    # ── Security ──
    Atom(
        "audit",
        "Security Audit",
        "Dependency vulnerability scanning",
        required_targets=["audit"],
        iso=[ISOMapping("27001", "A.8.8", "Technical vulnerability management")],
    ),
    Atom(
        "license",
        "License Compliance",
        "Verify license headers and compliance",
        required_targets=["license-check"],
        optional_targets=["license-fix", "license-strip"],
        iso=[ISOMapping("27001", "A.8.12", "Data classification")],
    ),
    # ── Local Environment ──
    Atom(
        "start",
        "Start",
        "Start the project runtime",
        required_targets=["start", "local"],
        optional_targets=[
            "stop",
            "logs",
            "local-down",
            "local-logs",
        ],
        iso=[ISOMapping("9001", "7.1.3", "Infrastructure")],
    ),
    Atom(
        "logs",
        "Logs",
        "Tail runtime logs",
        required_targets=["logs", "local-logs"],
        optional_targets=["local-logs-api"],
    ),
    Atom(
        "stop",
        "Stop",
        "Stop the project runtime",
        required_targets=["stop", "local-down"],
        optional_targets=["local-reset"],
    ),
    # ── Database ──
    Atom(
        "db-migrate",
        "DB Migrate",
        "Run database schema migrations",
        required_targets=["migrate"],
        optional_targets=["alembic-auto", "alembic-check", "db-revision"],
        iso=[ISOMapping("27001", "A.8.32", "Change management")],
    ),
    Atom(
        "db-reset",
        "DB Reset",
        "Drop and recreate the database",
        required_targets=["db-reset"],
        optional_targets=[],
    ),
    # ── Seed Data ──
    Atom(
        "seed",
        "Seed",
        "Populate development data",
        required_targets=["seed"],
        optional_targets=["seed-reset", "seed-large", "seed-ultra"],
    ),
    # ── Code Generation ──
    Atom(
        "codegen",
        "Code Generation",
        "Generate API clients or other artifacts from schemas",
        required_targets=["api-client", "openapi"],  # accept either
        optional_targets=["py-client"],
    ),
    # ── Build & Publish ──
    Atom(
        "build",
        "Build",
        "Build software artifacts (Docker, bundle, binary, wheel)",
        required_targets=["build"],
        iso=[ISOMapping("9001", "8.5.1", "Control of production")],
    ),
    Atom(
        "publish",
        "Publish",
        "Publish artifacts to registry, CDN, or store",
        required_targets=["publish"],
        iso=[ISOMapping("9001", "8.6", "Release of products")],
    ),
    # ── Deploy & Operations ──
    Atom(
        "deploy",
        "Deploy",
        "Deploy to target environment",
        required_targets=["deploy"],
        iso=[ISOMapping("27001", "A.8.32", "Change management")],
    ),
    Atom(
        "backup",
        "Backup",
        "Database and volume backup",
        required_targets=["backup"],
        iso=[ISOMapping("27001", "A.8.13", "Information backup")],
    ),
    Atom(
        "rollback",
        "Rollback",
        "Revert to previous deployment",
        required_targets=["rollback"],
        iso=[ISOMapping("27001", "A.8.32", "Change management")],
    ),
    Atom(
        "monitoring",
        "Monitoring",
        "Health checks and observability",
        required_targets=["health", "status"],  # accept either
        iso=[ISOMapping("27001", "A.8.15", "Logging")],
    ),
    # ── CI Aggregate ──
    Atom(
        "ci",
        "CI Gate",
        "Full CI pipeline aggregate (format + lint + test + audit)",
        required_targets=["ci"],
        iso=[
            ISOMapping("27001", "A.8.25", "Secure development lifecycle"),
            ISOMapping("9001", "8.7", "Control of nonconforming outputs"),
        ],
    ),
    # ── Compliance ──
    Atom(
        "compliance",
        "Compliance Evidence",
        "Generate ISO audit artifacts",
        required_targets=["compliance-report"],
        iso=[
            ISOMapping("9001", "9.1", "Monitoring, measurement"),
            ISOMapping("27001", "A.18.2", "Compliance with security policies"),
        ],
    ),
    # ── Help ──
    Atom("help", "Help", "Self-documenting target listing", required_targets=["help"]),
    # ── Clean ──
    Atom(
        "clean",
        "Clean",
        "Remove build artifacts and caches",
        required_targets=["clean"],
    ),
]

ATOMS_BY_ID: dict[str, Atom] = {a.id: a for a in ATOMS}


# ── Facets ───────────────────────────────────────────────────────────────────
# Required atoms gate the facet. Optional atoms are tracked but don't block.
# Grounded in reality: L2 should be achievable by network today.

FACETS: list[Facet] = [
    Facet(
        "code-quality",
        "Code Quality",
        "Is the code clean?",
        atom_refs=[
            FacetAtomRef("lint", required=True),
            FacetAtomRef("format", required=False),  # network doesn't have it yet
            FacetAtomRef("typecheck", required=False),  # not all stacks
        ],
    ),
    Facet(
        "verification",
        "Verification",
        "Is the code correct and safe?",
        atom_refs=[
            FacetAtomRef("test", required=True),
            FacetAtomRef("audit", required=False),  # aspirational, network lacks it
            FacetAtomRef("license", required=False),  # only some projects need it
        ],
    ),
    Facet(
        "runtime-control",
        "Runtime Control",
        "Can I start, stop, and inspect the runtime?",
        atom_refs=[
            FacetAtomRef("start", required=True),
            FacetAtomRef("stop", required=False),
            FacetAtomRef("logs", required=False),
            FacetAtomRef("db-migrate", required=False),  # not all systems have a DB
            FacetAtomRef("db-reset", required=False),
            FacetAtomRef("seed", required=False),  # not all systems need seed
            FacetAtomRef("help", required=False),
        ],
    ),
    Facet(
        "codegen",
        "Code Generation",
        "Are generated artifacts current?",
        atom_refs=[
            FacetAtomRef("deps", required=True),
            FacetAtomRef("codegen", required=False),  # only API+client combos
        ],
    ),
    Facet(
        "ci-gate",
        "CI Gate",
        "Can this merge?",
        composes_from=["code-quality", "verification"],
    ),
    Facet(
        "build-lifecycle",
        "Build Lifecycle",
        "Can I ship it?",
        atom_refs=[
            FacetAtomRef("build", required=True),
            FacetAtomRef("publish", required=False),
            FacetAtomRef("clean", required=False),
        ],
    ),
    Facet(
        "deployment",
        "Deployment",
        "Is it running safely?",
        atom_refs=[
            FacetAtomRef("deploy", required=True),
            FacetAtomRef("backup", required=False),
            FacetAtomRef("rollback", required=False),
            FacetAtomRef("monitoring", required=False),
        ],
    ),
    Facet(
        "compliance",
        "Compliance",
        "Can we pass an audit?",
        atom_refs=[
            FacetAtomRef("ci", required=True),
            FacetAtomRef("compliance", required=False),  # the explicit evidence gen
            FacetAtomRef("license", required=False),
        ],
        composes_from=["ci-gate", "build-lifecycle", "deployment"],
    ),
    Facet(
        "full-dev-lifecycle",
        "Full Dev Lifecycle",
        "Everything a developer needs",
        composes_from=["runtime-control", "codegen", "ci-gate"],
    ),
    Facet(
        "full-automation",
        "Full Automation",
        "Everything",
        composes_from=[
            "full-dev-lifecycle",
            "build-lifecycle",
            "deployment",
            "compliance",
        ],
    ),
]

FACETS_BY_ID: dict[str, Facet] = {f.id: f for f in FACETS}


# ── Levels ───────────────────────────────────────────────────────────────────
# Designed so that:
# - network (as-is) → L2
# - cloud (as-is) → L3
# - cloud + deploy → L4
# - cloud + deploy + compliance-report → L5

LEVELS: list[Level] = [
    Level("L0", "Bootstrap", "New project, nothing yet", []),
    Level(
        "L1",
        "Runnable",
        "Can start, stop, and inspect the runtime",
        ["runtime-control"],
    ),
    Level(
        "L2",
        "Quality",
        "Has CI quality gates",
        ["runtime-control", "code-quality", "verification"],
    ),
    Level(
        "L3",
        "Shippable",
        "Can build and publish artifacts",
        [
            "runtime-control",
            "code-quality",
            "verification",
            "codegen",
            "build-lifecycle",
        ],
    ),
    Level(
        "L4",
        "Operational",
        "Automated deploy pipeline",
        [
            "runtime-control",
            "code-quality",
            "verification",
            "codegen",
            "build-lifecycle",
            "deployment",
        ],
    ),
    Level(
        "L5",
        "Auditable",
        "ISO-ready with evidence",
        [
            "runtime-control",
            "code-quality",
            "verification",
            "codegen",
            "build-lifecycle",
            "deployment",
            "compliance",
        ],
    ),
]


# ── Resolution helpers ───────────────────────────────────────────────────────


def resolve_facet_required_atoms(facet_id: str) -> list[str]:
    """Resolve only the REQUIRED atom IDs for a facet (recursive)."""
    facet = FACETS_BY_ID.get(facet_id)
    if not facet:
        return []
    atoms = [ref.atom_id for ref in facet.atom_refs if ref.required]
    for sub_id in facet.composes_from:
        atoms.extend(resolve_facet_required_atoms(sub_id))
    return atoms


def resolve_facet_all_atoms(facet_id: str) -> list[tuple[str, bool]]:
    """Resolve ALL atom IDs with required flag (recursive)."""
    facet = FACETS_BY_ID.get(facet_id)
    if not facet:
        return []
    atoms = [(ref.atom_id, ref.required) for ref in facet.atom_refs]
    for sub_id in facet.composes_from:
        atoms.extend(resolve_facet_all_atoms(sub_id))
    return atoms


def check_atom_satisfied(atom_id: str, available_targets: set[str]) -> bool:
    """Check if an atom is satisfied: at least one required target must exist."""
    atom = ATOMS_BY_ID.get(atom_id)
    if not atom:
        return False
    return any(t in available_targets for t in atom.required_targets)


def determine_level(available_targets: set[str]) -> str:
    """Determine the highest maturity level from available Make targets."""

    def facet_ok(facet_id: str) -> bool:
        required_atoms = resolve_facet_required_atoms(facet_id)
        return all(check_atom_satisfied(a, available_targets) for a in required_atoms)

    achieved = "L0"
    for lv in LEVELS:
        if all(facet_ok(f) for f in lv.facet_ids):
            achieved = lv.id
    return achieved


# ── Multi-strategy resolution ─────────────────────────────────────────────────


def check_resolve_rule(
    rule: ResolveRule, *, make_targets: set[str], docs_root: Path | None = None
) -> bool:
    """Check if a single resolve rule is satisfied.

    Args:
        rule: The resolution rule to check.
        make_targets: Available Make targets (for strategy="make").
        docs_root: Path to docs/ directory (for strategy="path", "file-content").
    """
    if rule.strategy == "make":
        if rule.any_of:
            return any(t in make_targets for t in rule.any_of)
        if rule.all_of:
            return all(t in make_targets for t in rule.all_of)
        return False

    if rule.strategy == "path" and docs_root:
        if rule.all_of:
            return all((docs_root / p).exists() for p in rule.all_of)
        if rule.any_of:
            return any((docs_root / p).exists() for p in rule.any_of)
        return False

    if rule.strategy == "field" and rule.file and docs_root:
        file_path = docs_root.parent / rule.file  # forktex.json is at project root
        if not file_path.exists():
            return False
        try:
            data = json.loads(file_path.read_text())
            parts = (rule.path or "").split(".")
            for part in parts:
                if isinstance(data, dict):
                    data = data.get(part)
                else:
                    return False
            return data is not None
        except (json.JSONDecodeError, KeyError):
            return False

    return False


def check_atom_resolved(
    atom: Atom, *, make_targets: set[str], docs_root: Path | None = None
) -> bool:
    """Check if an atom is satisfied using multi-strategy resolution.

    An atom is satisfied if ANY of its resolve rules passes.
    Falls back to required_targets check if no resolve rules defined.
    """
    if atom.resolve:
        return any(
            check_resolve_rule(rule, make_targets=make_targets, docs_root=docs_root)
            for rule in atom.resolve
        )
    # v1 fallback
    return any(t in make_targets for t in atom.required_targets)


def load_standard(
    standard_path: Path,
) -> tuple[list[Domain], list[Atom], list[Facet], list[Level]]:
    """Load the standard from standard.json.

    Returns (domains, atoms, facets, levels) with full resolution rules.
    """
    data = json.loads(standard_path.read_text())

    domains = [
        Domain(
            id=d["id"],
            name=d["name"],
            description=d["description"],
            track=d["track"],
            scope=d["scope"],
        )
        for d in data.get("domains", [])
        if not d.get("_comment")
    ]

    atoms = []
    for a in data.get("atoms", []):
        if a.get("_comment"):
            continue
        resolve_rules = []
        for r in a.get("resolve", []):
            resolve_rules.append(
                ResolveRule(
                    strategy=r["strategy"],
                    any_of=r.get("any_of", []),
                    all_of=r.get("all_of", []),
                    file=r.get("file"),
                    path=r.get("path"),
                )
            )
        # Derive v1 required_targets from make rules for backward compat
        make_any = []
        for r in resolve_rules:
            if r.strategy == "make":
                make_any.extend(r.any_of)
        iso_mappings = []
        for iso_str in a.get("iso", []):
            parts = iso_str.split(":")
            if len(parts) == 2:
                iso_mappings.append(ISOMapping(parts[0], parts[1], ""))
        atoms.append(
            Atom(
                id=a["id"],
                name=a["name"],
                description=a["description"],
                domain=a.get("domain", ""),
                resolve=resolve_rules,
                iso=iso_mappings,
                evidence=a.get("evidence", ""),
                required_targets=make_any,
            )
        )

    facets = []
    for f in data.get("facets", []):
        if f.get("_comment"):
            continue
        atom_refs = [
            FacetAtomRef(atom_id=ar["ref"], required=ar.get("required", True))
            for ar in f.get("atoms", [])
        ]
        facets.append(
            Facet(
                id=f["id"],
                name=f["name"],
                question=f["question"],
                domain=f.get("domain", ""),
                atom_refs=atom_refs,
                composes_from=f.get("composesFrom", []),
            )
        )

    levels = [
        Level(
            id=lv["id"],
            name=lv["name"],
            description=lv["description"],
            facet_ids=lv["facets"],
        )
        for lv in data.get("levels", [])
    ]

    return domains, atoms, facets, levels
