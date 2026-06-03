# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""forktex crafts + executes a multi-agent plan (in-process tier)."""

from __future__ import annotations

import pytest

from forktex.agent.tools.base import ToolResult
from forktex.agent.workflow import executor as executor_mod
from forktex.agent.workflow.craft import _normalize
from forktex.agent.workflow.executor import (
    InProcessExecutor,
    PlanRunResult,
    select_executor,
)
from forktex.agent.workflow.plan import Plan
from forktex.agent.workflow.sub_agent import SubAgentResult


class FakeToolServer:
    def __init__(self, error_tools=()):
        self.calls: list[tuple[str, dict]] = []
        self._error_tools = set(error_tools)

    def get_schemas(self):
        return [
            {"name": n, "description": "", "parameters": {}}
            for n in ("read_file", "grep_search", "bash_execute", "write_file")
        ]

    async def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name in self._error_tools:
            return ToolResult(content=f"{name} blew up", is_error=True)
        return ToolResult(content=f"ran {name}")


def _plan(*steps, **top):
    data = {
        "intent": top.get("intent", "do the thing"),
        "rationale": "because",
        "expected_outcome": "done",
        "requires_approval": False,
        "steps": list(steps),
    }
    return Plan.from_dict(_normalize(data))


@pytest.mark.asyncio
async def test_executes_steps_in_order(monkeypatch):
    spawned: list[str] = []

    async def fake_spawn(spec, *, parent_intelligence, parent_tool_server, on_tool_event=None):
        spawned.append(spec.intent)
        return SubAgentResult(name=spec.name, status="completed", summary="mapped it", rounds_used=2)

    monkeypatch.setattr(executor_mod, "spawn_sub_agent", fake_spawn)

    ts = FakeToolServer()
    plan = _plan(
        {"kind": "sub_agent", "payload": {"role": "researcher", "intent": "find callers"}},
        {"kind": "shell", "payload": {"command": "pytest -q"}},
        {"kind": "tool_call", "payload": {"tool": "read_file", "arguments": {"path": "x.py"}}},
    )
    result = await InProcessExecutor(object(), ts).execute(plan)

    assert isinstance(result, PlanRunResult)
    assert result.status == "completed"
    assert [s.kind for s in result.steps] == ["sub_agent", "tool_call", "tool_call"]
    assert result.steps[0].summary == "mapped it"
    assert spawned == ["find callers"]
    assert ("bash_execute", {"command": "pytest -q"}) in ts.calls


@pytest.mark.asyncio
async def test_prior_step_findings_feed_forward(monkeypatch):
    # A later sub-agent must receive earlier steps' summaries (plans are static,
    # so an editor can't see a researcher's findings otherwise).
    addenda: list[str] = []

    async def fake_spawn(spec, *, parent_intelligence, parent_tool_server, on_tool_event=None):
        addenda.append(spec.system_prompt_addendum)
        summary = "FSD lives in compliance/fsd/README.md" if spec.name == "researcher" else "wrote it"
        return SubAgentResult(name=spec.name, status="completed", summary=summary)

    monkeypatch.setattr(executor_mod, "spawn_sub_agent", fake_spawn)

    plan = _plan(
        {"kind": "sub_agent", "payload": {"role": "researcher", "intent": "find FSD docs"}},
        {"kind": "sub_agent", "payload": {"role": "editor", "intent": "add a scope line"}},
    )
    await InProcessExecutor(object(), FakeToolServer()).execute(plan)

    assert addenda[0] == ""  # researcher had no prior context
    assert "compliance/fsd/README.md" in addenda[1]  # editor sees the researcher's finding


@pytest.mark.asyncio
async def test_failing_step_stops_and_surfaces_rollback():
    ts = FakeToolServer(error_tools={"write_file"})
    plan = _plan(
        {"kind": "tool_call", "payload": {"tool": "read_file", "arguments": {}}},
        {
            "kind": "file_edit",
            "payload": {"path": "a.md", "operation": "create", "body": "hi"},
            "rollback": "git checkout a.md",
        },
        {"kind": "shell", "payload": {"command": "echo never"}},
    )
    result = await InProcessExecutor(object(), ts).execute(plan)

    assert result.status == "failed"
    assert result.failed_index == 1
    assert result.rollback_hint == "git checkout a.md"
    # The third step must NOT have run.
    assert all(cmd != "echo never" for _, kw in ts.calls for cmd in [kw.get("command")])


@pytest.mark.asyncio
async def test_sub_agent_role_normalized_and_intersected(monkeypatch):
    captured = {}

    async def fake_spawn(spec, *, parent_intelligence, parent_tool_server, on_tool_event=None):
        captured["subset"] = set(spec.tool_subset)
        return SubAgentResult(name=spec.name, status="completed", summary="ok")

    monkeypatch.setattr(executor_mod, "spawn_sub_agent", fake_spawn)

    plan = _plan({"kind": "sub_agent", "payload": {"role": "researcher", "intent": "x"}})
    await InProcessExecutor(object(), FakeToolServer()).execute(plan)

    # researcher's subset intersected with the parent's actual tools.
    assert "read_file" in captured["subset"] and "grep_search" in captured["subset"]
    assert "graph_summary" not in captured["subset"]  # parent doesn't expose it


def test_normalize_expands_role():
    data = _normalize(
        {"steps": [{"kind": "sub_agent", "payload": {"role": "editor", "intent": "edit"}}]}
    )
    payload = data["steps"][0]["payload"]
    assert payload["name"] == "editor"
    assert "write_file" in payload["tool_subset"]


def test_normalize_coerces_role_used_as_kind():
    # Models sometimes emit kind="editor" instead of kind="sub_agent"+role.
    data = _normalize(
        {"steps": [{"kind": "editor", "intent": "write the file", "payload": {}}]}
    )
    step = data["steps"][0]
    assert step["kind"] == "sub_agent"
    assert step["payload"]["role"] == "editor"
    assert step["payload"]["intent"] == "write the file"
    # And it parses into a valid Plan.
    plan = Plan.from_dict(
        {
            "intent": "x",
            "rationale": "y",
            "expected_outcome": "z",
            "steps": data["steps"],
        }
    )
    assert plan.steps[0].kind == "sub_agent"


def test_select_executor_defaults_in_process(monkeypatch):
    monkeypatch.delenv("FORKTEX_FLOW_DB", raising=False)
    monkeypatch.setattr(executor_mod, "resolve_flow_db", lambda: None)
    ex = select_executor(object(), FakeToolServer())
    assert isinstance(ex, InProcessExecutor)
