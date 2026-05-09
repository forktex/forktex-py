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

"""Tests for ``forktex.agent.intelligence.grounding`` — the chat-agent
system-prompt assembler."""

from __future__ import annotations

import json
from pathlib import Path

import forktex.fsd  # noqa: F401  warm-up; see test_manifest_overlay rationale

from forktex.agent.intelligence.grounding import (
    DEFAULT_BASE,
    build_system_prompt,
)


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_bundle(root: Path, payload: dict) -> None:
    bundle = root / ".forktex" / "manual" / "manual_bundle.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(json.dumps(payload), encoding="utf-8")


# ── empty project ─────────────────────────────────────────────────────────


def test_empty_project_returns_default_base(tmp_path):
    prompt = build_system_prompt(tmp_path)
    assert DEFAULT_BASE in prompt
    # No grounding sources → user gets a hint about `forktex manual build`.
    assert "forktex manual build" in prompt


def test_custom_base_overrides_default(tmp_path):
    prompt = build_system_prompt(tmp_path, base_prompt="Persona X.")
    assert prompt.startswith("Persona X.")
    assert DEFAULT_BASE not in prompt


# ── AGENTS.md ─────────────────────────────────────────────────────────────


def test_root_agents_md_is_injected(tmp_path):
    _write(tmp_path / "AGENTS.md", "# Project conventions\n- prefer atoms.")
    prompt = build_system_prompt(tmp_path)
    assert "## Project Conventions (from AGENTS.md)" in prompt
    assert "prefer atoms" in prompt


def test_docs_agents_md_fallback(tmp_path):
    """When root AGENTS.md is missing, docs/AGENTS.md is read instead."""
    _write(tmp_path / "docs" / "AGENTS.md", "doc-side rules")
    prompt = build_system_prompt(tmp_path)
    assert "doc-side rules" in prompt


def test_root_agents_md_takes_precedence_over_docs(tmp_path):
    _write(tmp_path / "AGENTS.md", "ROOT WINS")
    _write(tmp_path / "docs" / "AGENTS.md", "DOCS LOSES")
    prompt = build_system_prompt(tmp_path)
    assert "ROOT WINS" in prompt
    assert "DOCS LOSES" not in prompt


def test_oversized_agents_md_is_truncated(tmp_path):
    huge = "x" * 50_000
    _write(tmp_path / "AGENTS.md", huge)
    prompt = build_system_prompt(tmp_path, max_chars=10_000)
    assert len(prompt) <= 10_000
    assert "[truncated]" in prompt


# ── manual bundle ─────────────────────────────────────────────────────────


def test_cached_bundle_rules_and_concepts_are_injected(tmp_path):
    _write_bundle(
        tmp_path,
        {
            "scope": "default",
            "project_name": "test",
            "generated_at": "2026-05-09T00:00:00Z",
            "rules": ["never push to master", "always run make gate"],
            "concepts": [
                {"name": "graph", "kind": "fsd-atom", "summary": "module graph"},
                {"name": "manual", "kind": "fsd-atom", "summary": "AI bundle"},
            ],
            "few_shots": [
                {"task": "Run gate", "command": "make gate", "expected": "green"},
            ],
        },
    )
    prompt = build_system_prompt(tmp_path)
    assert "## Project Rules" in prompt
    assert "never push to master" in prompt
    assert "## Key Concepts" in prompt
    assert "**graph**" in prompt
    assert "## Common Tasks" in prompt
    assert "make gate" in prompt
    # Hint shouldn't appear when we have a real bundle.
    assert "Run `forktex manual build`" not in prompt


def test_missing_bundle_emits_hint(tmp_path):
    """No bundle file → hint suggesting `forktex manual build`."""
    prompt = build_system_prompt(tmp_path)
    assert "forktex manual build" in prompt


def test_malformed_bundle_is_ignored(tmp_path):
    """A bundle file with bad JSON shouldn't crash the chat boot."""
    bundle = tmp_path / ".forktex" / "manual" / "manual_bundle.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text("{not json")
    prompt = build_system_prompt(tmp_path)
    # Falls through to "no bundle" path → hint appears.
    assert "forktex manual build" in prompt


def test_bundle_without_rules_or_concepts_is_silent(tmp_path):
    """Empty arrays inside the bundle don't render section headers."""
    _write_bundle(
        tmp_path,
        {
            "scope": "default",
            "project_name": "test",
            "generated_at": "2026-05-09T00:00:00Z",
            "rules": [],
            "concepts": [],
            "few_shots": [],
        },
    )
    prompt = build_system_prompt(tmp_path)
    assert "## Project Rules" not in prompt
    assert "## Key Concepts" not in prompt
    assert "## Common Tasks" not in prompt
    # But because the bundle exists, the "missing-bundle" hint is suppressed.
    assert "Run `forktex manual build`" not in prompt


# ── caps ──────────────────────────────────────────────────────────────────


def test_max_chars_is_honored_total(tmp_path):
    _write(tmp_path / "AGENTS.md", "y" * 30_000)
    prompt = build_system_prompt(tmp_path, max_chars=5_000)
    assert len(prompt) <= 5_000


def test_truncation_marker_present_when_capped(tmp_path):
    _write(tmp_path / "AGENTS.md", "y" * 30_000)
    prompt = build_system_prompt(tmp_path, max_chars=2_000)
    assert "[truncated]" in prompt
