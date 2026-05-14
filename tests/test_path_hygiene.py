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

"""Path-hygiene regression test.

Prevents the class of bug where a hardcoded developer-workstation path
(``/home/samanu/...``) or a duplicated project-root walk silently passes
locally but breaks on a fresh runner.

Every rule here was added in response to a real CI failure or refactor —
do not weaken without strong reason.
"""

from __future__ import annotations

import re

import pytest

from forktex.core.paths import require_project_root


REPO_ROOT = require_project_root(__file__)
SRC = REPO_ROOT / "src"
TESTS = REPO_ROOT / "tests"

# ``re.compile`` so the test file's own literals don't trip the scan —
# we look for them in *other* files, not in our own source.
_USER_HOME_RE = re.compile(r'["\'](/home/[^/"\']+|/Users/[^/"\']+)/')
_TMP_FORKTEX_RE = re.compile(r'["\']/tmp/forktex-[^"\']*["\']')


def _iter_py_files():
    for base in (SRC, TESTS):
        for path in sorted(base.rglob("*.py")):
            if path.name == "test_path_hygiene.py":
                continue
            yield path


def test_no_hardcoded_user_home_paths():
    """No file may embed ``/home/<user>/...`` or ``/Users/<user>/...``
    as a string literal. Use ``require_project_root(__file__)`` for the
    repo root, ``Path.home()`` for the user's home, or the helpers in
    ``forktex.core.paths`` for canonical ForkTex locations.

    Caught the ``/home/samanu/Desktop/forktex/forktex-py`` hardcoded
    PROJECT_ROOT in two test files that passed locally on the author's
    workstation but failed on GitHub Actions where the runner home
    differs.
    """
    offenders: list[str] = []
    for path in _iter_py_files():
        text = path.read_text()
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _USER_HOME_RE.search(line):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"  {rel}:{line_no}: {line.strip()}")
    assert not offenders, (
        "hardcoded user-home absolute paths found — use "
        "forktex.core.paths helpers or Path.home() instead:\n" + "\n".join(offenders)
    )


def test_no_tmp_forktex_literals_outside_core_paths():
    """No file may embed a ``/tmp/forktex-…`` string literal.

    Such paths are fragile — they depend on writable ``/tmp`` and a
    specific naming scheme that varies across runners. Use the helpers
    in ``forktex.core.paths`` (which delegate to ``forktex_cloud.paths``
    for the V1 filesystem spec) instead.
    """
    offenders: list[str] = []
    for path in _iter_py_files():
        # The canonical paths module is allowed to define such literals
        # if it ever needs to — but currently it doesn't.
        if path.name == "paths.py" and path.parent.name == "core":
            continue
        text = path.read_text()
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _TMP_FORKTEX_RE.search(line):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"  {rel}:{line_no}: {line.strip()}")
    assert not offenders, (
        "/tmp/forktex-… literals found outside forktex.core.paths:\n"
        + "\n".join(offenders)
    )


def test_ecosystem_root_walk_defined_only_in_core_paths():
    """``find_ecosystem_root`` must live in exactly one place
    (``forktex.core.paths``). The walk-up-to-N-sibling-git-repos pattern
    was copy-pasted into three command modules before being centralized;
    catch the next attempt at duplication early.
    """
    definitions: list[str] = []
    pattern = re.compile(r"^\s*def\s+(_?find_ecosystem_root)\s*\(", re.MULTILINE)
    for path in _iter_py_files():
        text = path.read_text()
        for match in pattern.finditer(text):
            rel = path.relative_to(REPO_ROOT)
            definitions.append(f"  {rel}: def {match.group(1)}(...)")
    assert len(definitions) == 1 and "core/paths.py" in definitions[0], (
        "find_ecosystem_root must be defined exactly once, in "
        "src/forktex/core/paths.py. Current definitions:\n"
        + "\n".join(definitions or ["  (none — has it been removed by mistake?)"])
    )


def test_tests_use_require_project_root_for_repo_paths():
    """Tests that need the repo root must use
    ``require_project_root(__file__)`` rather than counting ``parents[N]``
    or hardcoding paths. This keeps the test idiom uniform and removes
    fragile parent-count arithmetic.
    """
    offenders: list[str] = []
    pattern = re.compile(
        r"Path\s*\(\s*__file__\s*\)\s*\.resolve\s*\(\s*\)\s*\.(?:parents\[\d+\]|parent\.parent)"
    )
    for path in sorted(TESTS.rglob("test_*.py")):
        if path.name == "test_path_hygiene.py":
            continue
        text = path.read_text()
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"  {rel}:{line_no}: {line.strip()}")
    assert not offenders, (
        "tests must use require_project_root(__file__) instead of "
        "Path(__file__).resolve().parent[s]... — see tests/test_core_paths.py "
        "for the idiom:\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    "regex,description",
    [
        (_USER_HOME_RE, "user-home regex catches /home/foo/ literal"),
        (_TMP_FORKTEX_RE, "/tmp/forktex regex catches /tmp/forktex-x literal"),
    ],
)
def test_hygiene_regexes_are_load_bearing(regex, description):
    """Self-test: the regexes actually match what they're meant to. If
    someone weakens them, this test fails before the scanning tests can
    silently start passing."""
    samples = {
        _USER_HOME_RE: '"/home/foo/bar"',
        _TMP_FORKTEX_RE: '"/tmp/forktex-creds"',
    }
    assert regex.search(samples[regex]), description
