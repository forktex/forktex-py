# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""The runtime-bound `spawn_sub_agent` delegate tool injected by AgentManager.

Pins: it appears only for can_spawn agents; invoking it folds the sub-agent
summary into a ToolResult; the requested role subset is intersected with the
parent's actual tools (graceful degrade); the sub-agent can't itself spawn; and
the parent's on_tool_event is threaded for nested visibility.
"""

from __future__ import annotations

import pytest

from forktex.agent.engine.events import AgentEvent, AgentEventType
from forktex.agent.manager import AgentManager
from forktex.agent.tools.base import ToolResult
from forktex.agent.workflow import sub_agent as sub_agent_mod
from forktex.agent.workflow.sub_agent import SubAgentResult, SubAgentSpec, _run_sub_agent


def _mgr(tmp_path, **kw) -> AgentManager:
    return AgentManager(str(tmp_path), client=object(), **kw)


def _server_for(mgr: AgentManager, type_name: str):
    return mgr._build_tool_server(mgr._type_registry.get(type_name))


# ── gating ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("type_name", ["developer", "assistant"])
def test_spawn_tool_present_for_spawning_agents(tmp_path, type_name):
    assert "spawn_sub_agent" in _server_for(_mgr(tmp_path), type_name).list_tools()


@pytest.mark.parametrize("type_name", ["researcher", "reviewer", "deployer"])
def test_spawn_tool_absent_for_non_spawning_agents(tmp_path, type_name):
    assert "spawn_sub_agent" not in _server_for(_mgr(tmp_path), type_name).list_tools()


# ── invoke + intersect + recursion guard ───────────────────────────────────


def _fake_spawn(captured):
    async def _spawn(spec, *, parent_intelligence, parent_tool_server, on_tool_event=None):
        captured["spec"] = spec
        captured["on_tool_event"] = on_tool_event
        return SubAgentResult(
            name=spec.name,
            status="completed",
            summary="found the call sites",
            tokens_used=42,
            rounds_used=2,
        )

    return _spawn


async def test_invoke_folds_summary_into_tool_result(tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(sub_agent_mod, "spawn_sub_agent", _fake_spawn(captured))

    server = _server_for(_mgr(tmp_path), "assistant")
    result = await server.get_tool("spawn_sub_agent").execute(
        role="researcher", intent="map where route_agent_type is called"
    )

    assert isinstance(result, ToolResult)
    assert result.is_error is False
    assert "found the call sites" in result.content
    assert "researcher" in result.content
    assert result.data["tokens"] == 42 and result.data["rounds"] == 2
    assert "read_file" in result.data["granted_tools"]


async def test_role_subset_intersected_with_narrow_parent(tmp_path, monkeypatch):
    # `developer` lacks graph tools — a researcher spawned from it degrades to
    # the read tools developer actually has, instead of hard-failing.
    captured: dict = {}
    monkeypatch.setattr(sub_agent_mod, "spawn_sub_agent", _fake_spawn(captured))

    server = _server_for(_mgr(tmp_path), "developer")
    result = await server.get_tool("spawn_sub_agent").execute(
        role="researcher", intent="x"
    )

    granted = set(result.data["granted_tools"])
    assert "read_file" in granted and "grep_search" in granted
    assert "graph_summary" not in granted  # developer never had it
    assert "graph_summary" not in captured["spec"].tool_subset


async def test_sub_agent_cannot_spawn(tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(sub_agent_mod, "spawn_sub_agent", _fake_spawn(captured))

    server = _server_for(_mgr(tmp_path), "assistant")
    await server.get_tool("spawn_sub_agent").execute(role="editor", intent="x")

    # The spec handed to the sub-agent never carries the spawn tool.
    assert "spawn_sub_agent" not in captured["spec"].tool_subset


async def test_unknown_role_is_a_clean_tool_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sub_agent_mod, "spawn_sub_agent", _fake_spawn({}))
    server = _server_for(_mgr(tmp_path), "assistant")
    result = await server.get_tool("spawn_sub_agent").execute(role="telepath", intent="x")
    assert result.is_error is True
    assert "telepath" in result.content


async def test_parent_on_tool_event_is_threaded(tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(sub_agent_mod, "spawn_sub_agent", _fake_spawn(captured))

    events: list = []
    mgr = _mgr(tmp_path, on_tool_event=lambda *a: events.append(a))
    server = _server_for(mgr, "assistant")
    await server.get_tool("spawn_sub_agent").execute(role="researcher", intent="x")

    assert callable(captured["on_tool_event"])


# ── nested-event prefixing (sub_agent.py) ───────────────────────────────────


class _FakeProvider:
    def __init__(self, scripts):
        self._scripts = list(scripts)

    def chat_stream(self, messages, *, system=None, tools=None):
        script = self._scripts.pop(0)

        async def _gen():
            for ev in script:
                yield ev

        return _gen()


class _FakeToolServer:
    def get_schemas(self):
        return [{"name": "read_file", "description": "", "parameters": {}}]

    async def call(self, name, **kwargs):
        return ToolResult(content="ok")


async def test_nested_tool_events_are_prefixed_with_subagent_name():
    seen: list[tuple[str, str]] = []
    provider = _FakeProvider(
        [
            [
                AgentEvent(
                    event=AgentEventType.TOOL_CALL,
                    data={"name": "read_file", "id": "c1", "arguments": {}},
                ),
                AgentEvent(event=AgentEventType.DONE, data={}),
            ],
            [
                AgentEvent(event=AgentEventType.DELTA, data={"text": "done"}),
                AgentEvent(event=AgentEventType.DONE, data={}),
            ],
        ]
    )
    spec = SubAgentSpec.for_role("researcher", "read a file")
    spec = spec.__class__(
        name=spec.name,
        intent=spec.intent,
        tool_subset=frozenset({"read_file"}),
        max_rounds=spec.max_rounds,
        timeout_s=spec.timeout_s,
    )

    await _run_sub_agent(
        spec,
        provider,
        _FakeToolServer(),
        on_tool_event=lambda kind, name, data: seen.append((kind, name)),
    )

    assert any(name == "researcher▸read_file" for _, name in seen)
