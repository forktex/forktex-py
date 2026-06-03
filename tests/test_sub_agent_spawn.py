# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""Sub-agent spawn — Phase B execution (run a bounded sub-agent via the engine).

Drives `_run_sub_agent` with a scripted fake `LLMProvider` + fake tool server
(no network), asserting the AgentResponse → SubAgentResult mapping and the
timeout / tool-subset boundaries. `spawn_sub_agent`'s Phase-A validation is also
checked.
"""

from __future__ import annotations

import asyncio

import pytest

from forktex.agent.engine.events import AgentEvent, AgentEventType
from forktex.agent.tools.base import ToolResult
from forktex.agent.workflow.sub_agent import (
    SubAgentSpec,
    _run_sub_agent,
    spawn_sub_agent,
)


def _delta(text: str) -> AgentEvent:
    return AgentEvent(event=AgentEventType.DELTA, data={"text": text})


def _tool_call(name: str, call_id: str, **args) -> AgentEvent:
    return AgentEvent(
        event=AgentEventType.TOOL_CALL,
        data={"name": name, "id": call_id, "arguments": args},
    )


def _done() -> AgentEvent:
    return AgentEvent(event=AgentEventType.DONE, data={})


class FakeProvider:
    """Scripted provider: each chat_stream call pops the next script entry."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.tools_seen: list = []

    def chat_stream(self, messages, *, system=None, tools=None):
        self.tools_seen.append(tools)
        script = self._scripts.pop(0)

        async def _gen():
            if isinstance(script, Exception):
                raise script
            if callable(script):  # a hang, to exercise timeout
                await script()
                return
            for ev in script:
                yield ev

        return _gen()


class FakeToolServer:
    def __init__(self):
        self.calls: list = []

    def get_schemas(self):
        return [
            {
                "name": "read_file",
                "description": "r",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "write_file",
                "description": "w",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    async def call(self, name, **kw):
        self.calls.append(name)
        return ToolResult(content=f"ran {name}")


_SPEC = SubAgentSpec(
    name="researcher", intent="find the auth flow", tool_subset=frozenset({"read_file"})
)


@pytest.mark.asyncio
async def test_run_sub_agent_completed():
    res = await _run_sub_agent(
        _SPEC, FakeProvider([[_delta("the auth flow is X"), _done()]]), FakeToolServer()
    )
    assert res.status == "completed"
    assert res.name == "researcher"
    assert "auth flow is X" in res.summary
    assert res.error is None


@pytest.mark.asyncio
async def test_run_sub_agent_tool_subset_filters_schemas():
    """The sub-agent only sees its tool_subset, even though the parent has more."""
    provider = FakeProvider([[_delta("done"), _done()]])
    await _run_sub_agent(_SPEC, provider, FakeToolServer())
    sent = provider.tools_seen[0]
    names = {t["name"] for t in (sent or [])}
    assert names == {"read_file"}  # write_file excluded by the subset


@pytest.mark.asyncio
async def test_run_sub_agent_tool_call_then_summary():
    tool_server = FakeToolServer()
    provider = FakeProvider(
        [
            [_tool_call("read_file", "c1", path="x"), _done()],
            [_delta("summary"), _done()],
        ]
    )
    res = await _run_sub_agent(_SPEC, provider, tool_server)
    assert res.status == "completed"
    assert tool_server.calls == ["read_file"]
    assert res.rounds_used >= 1


@pytest.mark.asyncio
async def test_run_sub_agent_timeout():
    async def _hang():
        await asyncio.sleep(1.0)

    spec = SubAgentSpec(name="r", intent="i", tool_subset=frozenset(), timeout_s=0.01)
    res = await _run_sub_agent(spec, FakeProvider([_hang]), FakeToolServer())
    assert res.status == "timeout"
    assert res.error and "timed out" in res.error


@pytest.mark.asyncio
async def test_spawn_validates_unknown_tool():
    bad = SubAgentSpec(
        name="r", intent="i", tool_subset=frozenset({"nonexistent_tool"})
    )
    with pytest.raises(ValueError, match="not on parent server"):
        await spawn_sub_agent(
            bad, parent_intelligence=object(), parent_tool_server=FakeToolServer()
        )
