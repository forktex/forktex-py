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

"""Tests for plan-mode typed contracts."""

from __future__ import annotations

import pytest

from forktex.agent.workflow import (
    Approval,
    FileEditStep,
    Plan,
    PlanStep,
    ShellStep,
    SubAgentStep,
    ToolCallStep,
)
from forktex.agent.workflow.plan import PlanParseError


# ── PlanStep typed payload enforcement ────────────────────────────────


def test_plan_step_kind_must_match_payload():
    """PlanStep(kind="tool_call") with a FileEditStep payload is a TypeError."""
    with pytest.raises(TypeError):
        PlanStep(
            kind="tool_call",
            payload=FileEditStep(path="x", operation="create", body=""),
        )


def test_plan_step_each_kind_with_correct_payload():
    PlanStep(kind="tool_call", payload=ToolCallStep(tool="t", arguments={}))
    PlanStep(kind="file_edit", payload=FileEditStep(path="x", operation="create"))
    PlanStep(kind="shell", payload=ShellStep(command="echo hi"))
    PlanStep(
        kind="sub_agent",
        payload=SubAgentStep(
            spec_name="r",
            spec_intent="i",
            spec_tool_subset=(),
            spec_system_prompt_addendum="",
            spec_max_rounds=1,
            spec_timeout_s=1.0,
        ),
    )


# ── Plan construction ────────────────────────────────────────────────


def test_plan_default_requires_approval():
    p = Plan(
        intent="t",
        rationale="r",
        steps=(),
        expected_outcome="e",
    )
    assert p.requires_approval is True


def test_plan_skip_approval_when_explicit():
    p = Plan(
        intent="t",
        rationale="r",
        steps=(),
        expected_outcome="e",
        requires_approval=False,
    )
    assert p.requires_approval is False


# ── Plan.from_llm_output parser ─────────────────────────────────────


_VALID_PLAN_JSON = """
{
    "intent": "Summarize README",
    "rationale": "User asked for a high-level project overview.",
    "expected_outcome": "Three-bullet summary",
    "requires_approval": false,
    "steps": [
        {
            "kind": "tool_call",
            "payload": {"tool": "read_file", "arguments": {"path": "README.md"}}
        }
    ]
}
"""


def test_parse_bare_json():
    plan = Plan.from_llm_output(_VALID_PLAN_JSON)
    assert plan.intent == "Summarize README"
    assert plan.requires_approval is False
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == "tool_call"
    assert isinstance(plan.steps[0].payload, ToolCallStep)
    assert plan.steps[0].payload.tool == "read_file"


def test_parse_json_inside_fenced_block():
    wrapped = (
        f"Here's the plan:\n```json\n{_VALID_PLAN_JSON.strip()}\n```\nLet me know."
    )
    plan = Plan.from_llm_output(wrapped)
    assert plan.intent == "Summarize README"


def test_parse_json_with_leading_prose():
    wrapped = f"Sure! {_VALID_PLAN_JSON}"
    plan = Plan.from_llm_output(wrapped)
    assert plan.intent == "Summarize README"


def test_parse_invalid_json_raises():
    with pytest.raises(PlanParseError):
        Plan.from_llm_output("this is not JSON at all")


def test_parse_missing_required_key_raises():
    bad = '{"intent": "x", "rationale": "y", "steps": []}'  # missing expected_outcome
    with pytest.raises(PlanParseError):
        Plan.from_llm_output(bad)


def test_parse_unknown_step_kind_raises():
    bad = """
    {
        "intent": "t", "rationale": "r", "expected_outcome": "e",
        "steps": [{"kind": "telepathy", "payload": {}}]
    }
    """
    with pytest.raises(PlanParseError):
        Plan.from_llm_output(bad)


def test_parse_each_step_kind():
    raw = """
    {
        "intent": "i", "rationale": "r", "expected_outcome": "e",
        "steps": [
            {"kind": "tool_call", "payload": {"tool": "x", "arguments": {}}},
            {"kind": "file_edit", "payload": {"path": "a", "operation": "create", "body": ""}},
            {"kind": "shell", "payload": {"command": "ls"}},
            {"kind": "sub_agent", "payload": {
                "name": "r", "intent": "find todos",
                "tool_subset": ["read_file"],
                "system_prompt_addendum": "", "max_rounds": 3, "timeout_s": 30.0
            }}
        ]
    }
    """
    plan = Plan.from_llm_output(raw)
    assert tuple(s.kind for s in plan.steps) == (
        "tool_call",
        "file_edit",
        "shell",
        "sub_agent",
    )


# ── Approval state machine ───────────────────────────────────────────


def test_approval_approve_basic():
    a = Approval(decision="approve")
    assert a.decision == "approve"
    assert a.edits is None


def test_approval_edit_requires_edits():
    with pytest.raises(ValueError):
        Approval(decision="edit")  # missing edits


def test_approval_non_edit_rejects_edits():
    step = PlanStep(kind="shell", payload=ShellStep(command="ls"))
    with pytest.raises(ValueError):
        Approval(decision="approve", edits=(step,))


def test_approval_edit_carries_revised_steps():
    step = PlanStep(kind="shell", payload=ShellStep(command="ls"))
    a = Approval(decision="edit", edits=(step,), reason="prefer ls")
    assert a.edits == (step,)
    assert a.reason == "prefer ls"
