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

"""Tests for ~/.forktex/registry.json read/write and Touch dedupe."""

import pytest

from forktex.graph import registry


pytestmark = pytest.mark.usefixtures("isolated_home")


def test_record_touch_creates_entry(project_root):
    registry.record_touch(
        project_root=project_root,
        rel_path="config.json",
        kind="settings",
        writer="test.case",
    )
    reg = registry.load()
    proj = reg.projects[str(project_root.resolve())]
    assert len(proj.touches) == 1
    assert proj.touches[0].rel_path == "config.json"
    assert proj.touches[0].kind == "settings"


def test_record_touch_dedupes_same_rel_path(project_root):
    for kind in ("first", "second", "third"):
        registry.record_touch(
            project_root=project_root,
            rel_path="config.json",
            kind=kind,
            writer="test.case",
        )
    reg = registry.load()
    proj = reg.projects[str(project_root.resolve())]
    # Single Touch — last write wins.
    assert len(proj.touches) == 1
    assert proj.touches[0].kind == "third"


def test_record_touch_global_separate(project_root):
    registry.record_touch(
        project_root=None,
        rel_path="cloud.json",
        kind="cloud",
        writer="test.case",
    )
    registry.record_touch(
        project_root=project_root,
        rel_path="config.json",
        kind="settings",
        writer="test.case",
    )
    reg = registry.load()
    assert len(reg.global_touches) == 1
    assert reg.global_touches[0].rel_path == "cloud.json"
    assert str(project_root.resolve()) in reg.projects


def test_save_load_roundtrip(project_root):
    registry.record_touch(
        project_root=project_root,
        rel_path="config.json",
        kind="settings",
    )
    reg1 = registry.load()
    registry.save(reg1)
    reg2 = registry.load()
    assert list(reg2.projects.keys()) == list(reg1.projects.keys())


def test_forget_project(project_root):
    registry.record_touch(
        project_root=project_root,
        rel_path="config.json",
        kind="settings",
    )
    assert registry.forget_project(project_root) is True
    reg = registry.load()
    assert str(project_root.resolve()) not in reg.projects
    # Idempotent: second call returns False.
    assert registry.forget_project(project_root) is False


def test_reconcile_existence(project_root, tmp_path):
    # One existing project, one non-existing.
    registry.record_touch(
        project_root=project_root,
        rel_path="config.json",
        kind="settings",
    )
    bogus = tmp_path / "ghost"
    bogus.mkdir()
    registry.record_touch(
        project_root=bogus,
        rel_path="config.json",
        kind="settings",
    )
    bogus.rmdir()

    present, missing = registry.reconcile_existence()
    present_roots = {p.root for p in present}
    missing_roots = {p.root for p in missing}
    assert str(project_root.resolve()) in present_roots
    assert str(bogus.resolve()) in missing_roots
