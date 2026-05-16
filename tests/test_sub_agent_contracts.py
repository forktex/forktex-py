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

"""Tests for sub-agent typed contracts + spawn entry-point validation."""

from __future__ import annotations

import pytest

from forktex.agent.workflow import (
    Artifact,
    SubAgentResult,
    SubAgentSpec,
    spawn_sub_agent,
)


# A sentinel object stands in for an Intelligence — spawn_sub_agent in
# Phase A only checks `parent_intelligence is not None`, so we don't
# need a real LLM client for the contract tests.
_FAKE_INTELLIGENCE = object()


# ── SubAgentSpec validation ──────────────────────────────────────────


def test_spec_requires_positive_budget():
    with pytest.raises(ValueError):
        SubAgentSpec(name="r", intent="i", tool_subset=frozenset(), max_rounds=0)
    with pytest.raises(ValueError):
        SubAgentSpec(name="r", intent="i", tool_subset=frozenset(), timeout_s=0)


def test_spec_requires_name_and_intent():
    with pytest.raises(ValueError):
        SubAgentSpec(name="", intent="i", tool_subset=frozenset())
    with pytest.raises(ValueError):
        SubAgentSpec(name="r", intent="", tool_subset=frozenset())


def test_spec_for_role_researcher_has_read_tools():
    spec = SubAgentSpec.for_role("researcher", intent="find todos")
    assert spec.name == "researcher"
    assert "read_file" in spec.tool_subset
    assert "grep_search" in spec.tool_subset
    # Researcher should not have write tools.
    assert "write_file" not in spec.tool_subset


def test_spec_for_role_editor_has_write_tools():
    spec = SubAgentSpec.for_role("editor", intent="patch module")
    assert "write_file" in spec.tool_subset
    assert "patch_file" in spec.tool_subset


def test_spec_for_role_unknown_raises():
    with pytest.raises(ValueError):
        SubAgentSpec.for_role("telepath", intent="read minds")


# ── SubAgentResult shape ─────────────────────────────────────────────


def test_result_minimal():
    r = SubAgentResult(name="r", status="completed", summary="done")
    assert r.status == "completed"
    assert r.artifacts == ()
    assert r.tokens_used == 0


def test_result_with_artifacts():
    artifact = Artifact(kind="file_change", summary="modified README")
    r = SubAgentResult(
        name="r",
        status="completed",
        summary="done",
        artifacts=(artifact,),
        tokens_used=42,
        rounds_used=2,
    )
    assert r.artifacts == (artifact,)
    assert r.tokens_used == 42


# ── spawn_sub_agent gating ───────────────────────────────────────────


class _FakeToolServer:
    """Minimal ToolServer surface — just get_schemas."""

    def __init__(self, tool_names: list[str]) -> None:
        self._tool_names = tool_names

    def get_schemas(self) -> list[dict]:
        return [{"name": n} for n in self._tool_names]


async def test_spawn_requires_parent_intelligence():
    spec = SubAgentSpec.for_role("researcher", intent="find todos")
    with pytest.raises(ValueError, match="parent Intelligence"):
        await spawn_sub_agent(
            spec,
            parent_intelligence=None,  # type: ignore[arg-type]
            parent_tool_server=_FakeToolServer(["read_file"]),
        )


async def test_spawn_requires_parent_tool_server():
    spec = SubAgentSpec.for_role("researcher", intent="find todos")
    with pytest.raises(ValueError, match="parent ToolServer"):
        await spawn_sub_agent(
            spec,
            parent_intelligence=_FAKE_INTELLIGENCE,
            parent_tool_server=None,
        )


async def test_spawn_gates_unavailable_tools():
    """Sub-agent requesting tools the parent doesn't have must fail fast."""
    spec = SubAgentSpec(
        name="custom",
        intent="do thing",
        tool_subset=frozenset({"read_file", "imaginary_tool"}),
    )
    parent_server = _FakeToolServer(["read_file"])
    with pytest.raises(ValueError, match="imaginary_tool"):
        await spawn_sub_agent(
            spec,
            parent_intelligence=_FAKE_INTELLIGENCE,
            parent_tool_server=parent_server,
        )


async def test_spawn_raises_not_implemented_on_happy_path():
    """Phase A: with valid inputs + tool set, spawn raises NotImplementedError."""
    spec = SubAgentSpec.for_role("researcher", intent="find todos")
    # Parent has ALL researcher tools.
    parent_server = _FakeToolServer(list(spec.tool_subset))
    with pytest.raises(NotImplementedError, match="Phase B"):
        await spawn_sub_agent(
            spec,
            parent_intelligence=_FAKE_INTELLIGENCE,
            parent_tool_server=parent_server,
        )
