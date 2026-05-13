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

"""Tests for forktex.graph.io_proxy: tracked_write, tracked_append, _classify."""

import pytest

from forktex.graph import io_proxy, registry


pytestmark = pytest.mark.usefixtures("isolated_home")


# ── _classify ─────────────────────────────────────────────────────────────


def test_classify_global_path(isolated_home):
    target = isolated_home / ".forktex" / "cloud.json"
    target.parent.mkdir(parents=True)
    target.touch()
    classified = io_proxy._classify(target)
    assert classified is not None
    scope, _base, rel = classified
    assert scope == "os"
    assert rel == "cloud.json"


def test_classify_project_path(project_root):
    target = project_root / ".forktex" / "config.json"
    target.touch()
    classified = io_proxy._classify(target)
    assert classified is not None
    scope, base, rel = classified
    assert scope == "project"
    assert base == project_root / ".forktex"
    assert rel == "config.json"


def test_classify_picks_innermost_in_nested_layout(monorepo_root):
    target = monorepo_root / "packages" / "api" / ".forktex" / "config.json"
    target.touch()
    classified = io_proxy._classify(target)
    assert classified is not None
    scope, base, rel = classified
    assert scope == "project"
    # The innermost .forktex (under packages/api) — not the outer one.
    assert base == monorepo_root / "packages" / "api" / ".forktex"
    assert rel == "config.json"


def test_classify_returns_none_for_non_forktex_path(tmp_path):
    target = tmp_path / "random" / "file.txt"
    target.parent.mkdir()
    target.touch()
    assert io_proxy._classify(target) is None


# ── tracked_write happy paths ────────────────────────────────────────────


def test_tracked_write_writes_and_records(project_root):
    target = project_root / ".forktex" / "config.json"
    io_proxy.tracked_write(
        target,
        '{"hello":"world"}\n',
        kind="settings",
        writer="test.case",
    )
    assert target.read_text() == '{"hello":"world"}\n'

    reg = registry.load()
    assert str(project_root) in reg.projects
    touches = reg.projects[str(project_root)].touches
    assert any(t.rel_path == "config.json" and t.kind == "settings" for t in touches)


def test_tracked_write_atomic_no_partial_files(project_root):
    """No .tmp files should remain after a successful write."""
    target = project_root / ".forktex" / "config.json"
    io_proxy.tracked_write(target, "x", kind="settings")
    leftovers = [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


# ── tracked_write enforcement ────────────────────────────────────────────


def test_tracked_write_rejects_unspec_path(project_root):
    target = project_root / ".forktex" / "rogue_file.txt"
    with pytest.raises(io_proxy.StructureViolation, match="rogue_file.txt"):
        io_proxy.tracked_write(target, "data", kind="rogue")


def test_tracked_write_lenient_mode_proceeds(project_root, caplog):
    target = project_root / ".forktex" / "rogue_file.txt"
    import logging

    caplog.set_level(logging.WARNING, logger="forktex.graph.io_proxy")
    io_proxy.tracked_write(target, "data", kind="rogue", lenient=True)
    assert target.read_text() == "data"
    assert any("rogue_file.txt" in rec.message for rec in caplog.records)


def test_tracked_write_lenient_via_env(project_root, monkeypatch):
    monkeypatch.setenv("FORKTEX_STRUCTURE_LENIENT", "1")
    target = project_root / ".forktex" / "rogue_file.txt"
    # No StructureViolation thanks to env override.
    io_proxy.tracked_write(target, "data", kind="rogue")
    assert target.is_file()


def test_tracked_write_outside_forktex_passthrough(tmp_path):
    """Non-.forktex paths should write but not touch the registry."""
    target = tmp_path / "outside.txt"
    io_proxy.tracked_write(target, "x", kind="raw")
    assert target.read_text() == "x"
    reg = registry.load()
    # No project root should be registered for tmp_path.
    assert str(tmp_path) not in reg.projects


# ── tracked_append ───────────────────────────────────────────────────────


def test_tracked_append_appends_jsonl(project_root):
    target = project_root / ".forktex" / "agents" / "history" / "abc.jsonl"
    io_proxy.tracked_append(
        target,
        '{"a":1}',
        kind="agent_history",
        writer="test.case",
    )
    io_proxy.tracked_append(
        target,
        '{"b":2}',
        kind="agent_history",
        writer="test.case",
    )
    lines = target.read_text().splitlines()
    assert lines == ['{"a":1}', '{"b":2}']

    reg = registry.load()
    touches = reg.projects[str(project_root)].touches
    assert any(t.rel_path == "agents/history/abc.jsonl" for t in touches)


def test_tracked_append_rejects_unspec_path(project_root):
    target = project_root / ".forktex" / "rogue.jsonl"
    with pytest.raises(io_proxy.StructureViolation):
        io_proxy.tracked_append(target, "x", kind="rogue")


# ── Registry side-effects ────────────────────────────────────────────────


def test_global_writes_record_under_global_touches(isolated_home):
    target = isolated_home / ".forktex" / "intelligence.json"
    io_proxy.tracked_write(
        target,
        "{}",
        kind="intelligence_settings",
        writer="test.case",
    )
    reg = registry.load()
    assert any(t.rel_path == "intelligence.json" for t in reg.global_touches)
    # Importantly the registry's own write doesn't recursively record itself.
    assert all(t.rel_path != registry.REGISTRY_FILENAME for t in reg.global_touches)
