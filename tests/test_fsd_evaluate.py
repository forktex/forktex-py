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

"""Regression tests for ``forktex.fsd.evaluate``.

The level evaluator must treat profile-disabled atoms as N/A
(``AtomStatus.OUT_OF_SCOPE``) for the purposes of level satisfaction —
matching the facet evaluator. Without this, switching a project to a
profile that disables a level-required atom (e.g. ``apply`` for
``package/python-library``) would silently drop the project from L4 →
L0 even though every applicable atom is satisfied.

This was the bug fixed in commit landing FSD v1.2.0 (`manual` atom,
`ci`→`gate` rename, profile alignment): facet eval already accepted
``OUT_OF_SCOPE``; level eval did not.
"""

from __future__ import annotations

from forktex.core.paths import require_project_root
from forktex.fsd.evaluate import AtomStatus, evaluate
from forktex.fsd.loader import load_standard
from forktex.manifest.models import ForktexManifest


PROJECT_ROOT = require_project_root(__file__)


def _all_make_targets_for(standard) -> set[str]:
    """Pretend every make-resolvable atom + variant is satisfied."""
    targets: set[str] = set()
    for atom in standard.atoms:
        for rule in atom.resolve:
            if rule.strategy == "make":
                targets.update(rule.any_of)
                targets.update(rule.all_of)
    # Plus the chord aliases.
    for chord in standard.aliases:
        targets.add(chord)
    return targets


def test_level_evaluator_treats_profile_disabled_atoms_as_satisfied(tmp_path):
    """Regression: with `package/python-library`, ops atoms are
    profile-disabled. They should report N/A and the level evaluator
    should still let the project reach L4 if `acceptance` is satisfied.

    Pre-fix bug: level eval required SATISFIED|SKIPPED, treating
    OUT_OF_SCOPE as a fail. Project dropped to L0.
    """
    standard = load_standard()
    manifest = ForktexManifest.load(PROJECT_ROOT / "forktex.json")

    # Pretend every declared make target is present — minus the obviously
    # disabled ones — so the only things blocking L4 would be N/A atoms.
    targets = _all_make_targets_for(standard)

    result = evaluate(
        standard,
        project_root=tmp_path,
        make_targets=targets,
        manifest=manifest,
    )

    # Profile-disabled atoms must report N/A.
    by_id = {a.id: a for a in result.atoms}
    for disabled_id in ("apply", "destroy", "monitor", "rollback", "backup"):
        assert disabled_id in by_id
        assert by_id[disabled_id].status is AtomStatus.OUT_OF_SCOPE, (
            f"{disabled_id} should be N/A under package/python-library, "
            f"got {by_id[disabled_id].status}"
        )

    # And the level evaluator should still award L4, treating those
    # N/A atoms as non-blocking.
    assert result.level == "L4", (
        f"expected L4 with profile-disabled atoms as N/A, got {result.level}"
    )


def test_level_evaluator_fails_when_required_atom_actually_missing():
    """Sanity check: a genuinely missing required atom must still block
    the level (the fix above is *only* about OUT_OF_SCOPE — FAILED stays
    a hard fail)."""
    standard = load_standard()
    manifest = ForktexManifest.load(PROJECT_ROOT / "forktex.json")

    # Drop `test` from the make-targets set. `test` is required at L2
    # (verification facet) and isn't profile-disabled — so its status
    # becomes FAILED, not OUT_OF_SCOPE.
    targets = _all_make_targets_for(standard) - {"test"}

    result = evaluate(
        standard,
        project_root=PROJECT_ROOT,  # real root so other atoms can resolve
        make_targets=targets,
        manifest=manifest,
    )

    by_id = {a.id: a for a in result.atoms}
    assert by_id["test"].status is AtomStatus.FAILED
    # L2 (Quality) needs `test`; level should be capped below L2.
    assert result.level in ("L0", "L1"), (
        f"expected level capped at L0/L1 when `test` fails, got {result.level}"
    )
