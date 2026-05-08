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

"""FSD standard catalog shape — software-only contract."""

from importlib import resources
from pathlib import Path

from forktex.fsd.models import FSDStandard


def _load() -> FSDStandard:
    with resources.path("forktex.data.fsd", "standard.json") as p:
        return FSDStandard.from_json(Path(p))


# Atom IDs that previously existed under org-side domains. These must
# never reappear in forktex-py's bundled catalog — forktex-py is a
# software-tooling library, not an organisational governance tool.
ORG_SIDE_FORBIDDEN = frozenset(
    {
        "org-description",
        "org-structure",
        "roles",
        "policy-infosec",
        "policy-quality",
        "asset-register",
        "risk-register",
        "interested-parties",
        "proc-sdlc",
        "proc-risk",
        "proc-incident",
        "proc-change",
        "proc-audit",
        "proc-corrective",
        "proc-document-control",
        "proc-bcp",
        "proc-supplier",
        "soa",
        "isms-scope",
        "legal-register",
        "fsd-compliance-matrix",
        "compliance-evidence",
        "supplier-register",
        "supplier-assessment",
        "cashflow-model",
        "pricing-model",
    }
)


def test_catalog_is_software_only():
    s = _load()
    assert {d.id for d in s.domains} == {"code", "data", "infra", "ops"}
    assert len(s.atoms) == 21
    assert {lvl.id for lvl in s.levels} == {"L0", "L1", "L2", "L3", "L4"}


def test_no_org_side_atoms_survived():
    s = _load()
    surviving = {a.id for a in s.atoms} & ORG_SIDE_FORBIDDEN
    assert not surviving, f"org-side atoms leaked: {surviving}"


def test_no_org_side_facets_survived():
    s = _load()
    forbidden_facets = {
        "org-foundation",
        "policy-framework",
        "register-framework",
        "core-procedures",
        "management-procedures",
        "support-procedures",
        "iso-framework",
        "supply-chain-mgmt",
        "financial-foundation",
        "full-governance",
        "full-process",
        "full-compliance",
    }
    surviving = {f.id for f in s.facets} & forbidden_facets
    assert not surviving, f"org-side facets leaked: {surviving}"


def test_no_l5_compliant_level():
    s = _load()
    assert "L5" not in {lvl.id for lvl in s.levels}


def test_chord_aliases_present_no_deprecated_aliases():
    """Hard break: deprecated rename aliases (start→apply, etc.) must
    not survive the cleanup; only chord aliases (quality, ci, release)
    remain."""
    s = _load()
    assert set(s.aliases.keys()) == {"quality", "ci", "release"}
    assert s.aliases_deprecated == {}


def test_software_atoms_carry_facet_membership():
    """Every atom in the bundled catalog declares an explicit facet —
    drives level rollup and the audit citation graph."""
    s = _load()
    missing = [a.id for a in s.atoms if not a.facet]
    assert not missing, f"atoms without facet: {missing}"
