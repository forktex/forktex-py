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

"""Lock the Python version range across pyproject, README, and CI matrix.

Three sources independently declare which Python versions forktex supports:

- pyproject.toml: requires-python lower bound + classifiers
- README.md: the "Tested on X, Y, Z" line in the Install section
- .github/workflows/ci.yml: the matrix.python-version array

If they drift apart, users see a published wheel that claims support for a
Python version CI never actually exercised. This test asserts all three
sources agree.
"""

from __future__ import annotations

import re
import tomllib

import pytest
import yaml

from forktex.core.paths import require_project_root

REPO_ROOT = require_project_root(__file__)


def _pyproject_versions() -> tuple[str, set[str]]:
    """Return (requires-python lower bound, classifier versions) from pyproject.toml."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    project = data["project"]

    requires = project["requires-python"]
    m = re.match(r">=\s*(\d+\.\d+)", requires)
    assert m, f"unexpected requires-python format: {requires!r}"
    lower = m.group(1)

    classifiers = {
        c.rsplit("::", 1)[1].strip()
        for c in project["classifiers"]
        if c.startswith("Programming Language :: Python ::")
        and re.fullmatch(r"\s*\d+\.\d+\s*", c.rsplit("::", 1)[1])
    }
    return lower, classifiers


def _readme_versions() -> tuple[str, set[str]]:
    """Return (lower bound, tested versions) from README.md."""
    text = (REPO_ROOT / "README.md").read_text()

    lower_match = re.search(r"Requires\s+\**Python\s+(\d+\.\d+)\+", text)
    assert lower_match, "README missing 'Requires Python X.Y+' marker"

    tested_match = re.search(r"Tested on ((?:\d+\.\d+)(?:,\s*\d+\.\d+)*)", text)
    assert tested_match, "README missing 'Tested on …' marker"
    tested = {v.strip() for v in tested_match.group(1).split(",")}

    return lower_match.group(1), tested


def _ci_matrix_versions() -> set[str]:
    """Return python-version matrix from ci.yml."""
    data = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    matrix = data["jobs"]["ci"]["strategy"]["matrix"]["python-version"]
    return {str(v) for v in matrix}


def test_pyproject_and_readme_agree_on_lower_bound():
    py_lower, _ = _pyproject_versions()
    readme_lower, _ = _readme_versions()
    assert py_lower == readme_lower, (
        f"pyproject requires-python ({py_lower}) and README "
        f"'Requires Python {readme_lower}+' disagree"
    )


def test_supported_versions_match_across_sources():
    _, py_classifiers = _pyproject_versions()
    _, readme_tested = _readme_versions()
    ci_matrix = _ci_matrix_versions()

    assert py_classifiers == readme_tested == ci_matrix, (
        "Python version sets disagree:\n"
        f"  pyproject classifiers: {sorted(py_classifiers)}\n"
        f"  README 'Tested on':    {sorted(readme_tested)}\n"
        f"  ci.yml matrix:         {sorted(ci_matrix)}"
    )


def test_lower_bound_is_in_supported_set():
    py_lower, py_classifiers = _pyproject_versions()
    assert py_lower in py_classifiers, (
        f"requires-python lower bound {py_lower} not present in classifiers "
        f"{sorted(py_classifiers)}"
    )


@pytest.mark.parametrize("source", ["pyproject", "readme", "ci"])
def test_no_unsupported_python_versions_listed(source: str):
    """All declared versions must be plausible (3.14+, not yet released > 3.20)."""
    if source == "pyproject":
        _, versions = _pyproject_versions()
    elif source == "readme":
        _, versions = _readme_versions()
    else:
        versions = _ci_matrix_versions()

    for v in versions:
        major, minor = (int(p) for p in v.split("."))
        assert major == 3 and 14 <= minor <= 20, (
            f"{source} lists implausible version: {v}"
        )
