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

"""Tests for the canonical structure spec + audit/audit_tree."""

import pytest

from forktex.graph import structure


# ── _matches: segment semantics + ** ──────────────────────────────────────


@pytest.mark.parametrize(
    "pattern,rel,expected",
    [
        ("config.json", "config.json", True),
        ("config.json", "other.json", False),
        ("vault/*/secrets.enc", "vault/dev/secrets.enc", True),
        ("vault/*/secrets.enc", "vault/dev/sub/secrets.enc", False),
        ("observability/**", "observability/loki/config.yaml", True),
        ("observability/**", "observability", True),
        ("observability/**", "elsewhere/foo", False),
        ("agents/history/*.jsonl", "agents/history/abc.jsonl", True),
        ("agents/history/*.jsonl", "agents/history/sub/abc.jsonl", False),
        ("docker-compose.*.yml", "docker-compose.dev.yml", True),
        ("data/*/**", "data/postgres/main/db.sql", True),
        ("conversation_*.json", "conversation_abc123.json", True),
    ],
)
def test_matches_segment_semantics(pattern, rel, expected):
    assert structure._matches(pattern, rel) is expected


# ── validate_path ────────────────────────────────────────────────────────


def test_validate_path_accepts_known_patterns():
    assert structure.validate_path("project", "config.json").ok
    assert structure.validate_path("project", ".version").ok
    assert structure.validate_path("project", ".gitignore").ok
    assert structure.validate_path("project", "instances/abc.json").ok
    assert structure.validate_path("os", "registry.json").ok
    assert structure.validate_path("os", "graph.json").ok


def test_validate_path_rejects_unknown_patterns():
    result = structure.validate_path("project", "rogue.txt")
    assert not result.ok
    assert "no spec entry" in result.reason


def test_validate_path_rejects_path_escape():
    assert not structure.validate_path("project", "../escape").ok


# ── audit on a single dir ────────────────────────────────────────────────


def test_audit_marks_required_missing(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / ".forktex").mkdir()
    # Missing both .version and .gitignore (required entries).
    results = structure.audit("project", root)
    missing = [r for r in results if r.status == "missing_required"]
    patterns = {r.rel_path for r in missing}
    assert ".version" in patterns
    assert ".gitignore" in patterns


def test_audit_classifies_known_files(project_root):
    (project_root / ".forktex" / ".gitignore").write_text("*\n!.gitignore\n")
    results = structure.audit("project", project_root)
    matched = [r for r in results if r.status == "matched"]
    by_rel = {r.rel_path for r in matched}
    assert ".version" in by_rel
    assert ".gitignore" in by_rel


def test_audit_marks_unknown_files(project_root):
    (project_root / ".forktex" / "rogue.txt").write_text("x")
    results = structure.audit("project", project_root)
    unknown = [r for r in results if r.status == "unknown"]
    assert any(r.rel_path == "rogue.txt" for r in unknown)


# ── audit_tree on a monorepo ─────────────────────────────────────────────


def test_audit_tree_emits_one_report_per_nested_forktex(monorepo_root):
    reports = structure.audit_tree(monorepo_root)
    roots = {r.project_root.resolve() for r in reports}
    assert (monorepo_root / "packages" / "api").resolve() in roots
    assert monorepo_root.resolve() in roots
    # packages/web has NO .forktex/ — should not produce a report.
    assert (monorepo_root / "packages" / "web").resolve() not in roots


def test_discover_nested_skips_heavy_trees(monorepo_root):
    (monorepo_root / "node_modules").mkdir()
    (monorepo_root / "node_modules" / ".forktex").mkdir()
    (monorepo_root / "node_modules" / ".forktex" / ".version").write_text("1\n")
    found = structure.discover_nested_forktex_dirs(monorepo_root)
    assert all("node_modules" not in p.parts for p in found)
