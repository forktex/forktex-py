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

# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""Behaviour guard for the agentic loop's turn cycle.

Drives ``AgentLoop`` with a scripted fake ``LLMProvider`` + fake tool server —
no network, no real LLM. The fake provider yields already-parsed ``AgentEvent``s
exactly as the real ``IntelligenceProvider`` does, so it injects directly as the
loop's provider.
"""

from __future__ import annotations

import pytest

from forktex.agent.engine import AgentLoop
from forktex.agent.engine import loop as loop_mod
from forktex.agent.engine.events import AgentEvent, AgentEventType
from forktex.agent.tools.base import ToolResult


def _delta(text: str) -> AgentEvent:
    return AgentEvent(event=AgentEventType.DELTA, data={"text": text})


def _tool_call(name: str, call_id: str, **arguments) -> AgentEvent:
    return AgentEvent(
        event=AgentEventType.TOOL_CALL,
        data={"name": name, "id": call_id, "arguments": arguments},
    )


def _done() -> AgentEvent:
    return AgentEvent(event=AgentEventType.DONE, data={})


class FakeProvider:
    """Scripted ``LLMProvider``: one entry per ``chat_stream`` call.

    Each script entry is either a list of ``AgentEvent``s (a successful stream)
    or an ``Exception`` instance (raised mid-stream to exercise retry).
    """

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls: list[dict] = []

    def chat_stream(self, messages, *, system=None, tools=None):
        self.calls.append(
            {"messages": [dict(m) for m in messages], "system": system, "tools": tools}
        )
        script = self._scripts.pop(0)

        async def _gen():
            if isinstance(script, Exception):
                raise script
            for ev in script:
                yield ev

        return _gen()


class FakeToolServer:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def get_schemas(self):
        return [
            {
                "name": "echo",
                "description": "echo a value",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            }
        ]

    async def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return ToolResult(content=f"ECHO:{kwargs.get('value', '')}")


def _loop(scripts, **kw):
    return AgentLoop(FakeProvider(scripts), FakeToolServer(), **kw)


@pytest.mark.asyncio
async def test_single_text_turn_terminates():
    loop = _loop([[_delta("hi "), _delta("there"), _done()]])
    resp = await loop.run_task("hello")
    assert resp.text == "hi there"
    assert resp.tool_calls_made == []
    assert resp.error is None
    assert [m["role"] for m in loop.conversation.messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_tool_call_then_final_text():
    tool_server = FakeToolServer()
    loop = AgentLoop(
        FakeProvider(
            [
                [_tool_call("echo", "c1", value="x"), _done()],
                [_delta("final"), _done()],
            ]
        ),
        tool_server,
    )
    resp = await loop.run_task("go")
    assert resp.text == "final"
    assert tool_server.calls == [("echo", {"value": "x"})]
    assert len(resp.tool_calls_made) == 1
    # user → assistant(tool_calls) → tool(result) → assistant(final)
    assert [m["role"] for m in loop.conversation.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert loop.conversation.messages[2]["content"] == "ECHO:x"


@pytest.mark.asyncio
async def test_multi_round_two_tool_calls():
    tool_server = FakeToolServer()
    loop = AgentLoop(
        FakeProvider(
            [
                [_tool_call("echo", "c1", value="a"), _done()],
                [_tool_call("echo", "c2", value="b"), _done()],
                [_delta("fin"), _done()],
            ]
        ),
        tool_server,
    )
    resp = await loop.run_task("go")
    assert resp.text == "fin"
    assert tool_server.calls == [("echo", {"value": "a"}), ("echo", {"value": "b"})]


@pytest.mark.asyncio
async def test_max_rounds_terminates_with_error():
    # Every round requests a tool call → loop exhausts max_tool_rounds.
    loop = _loop(
        [
            [_tool_call("echo", "c1", value="a"), _done()],
            [_tool_call("echo", "c2", value="b"), _done()],
        ],
        max_tool_rounds=2,
    )
    resp = await loop.run_task("go")
    # CURRENT behaviour: a synthetic ERROR event surfaces as resp.error.
    # Step 3 flips this to assert an AgentLoopExhausted is raised instead.
    assert resp.error is not None
    assert "2 tool rounds" in resp.error


@pytest.mark.asyncio
async def test_empty_stream_surfaces_error():
    # Provider opens the stream then yields only DONE — no text, no tools, no
    # tokens (the incapable-model / errored-stream case). Must surface an error,
    # not finish silently "completed" with empty output.
    loop = _loop([[_done()]])
    resp = await loop.run_task("review the docs")
    assert resp.error is not None
    assert "empty response" in resp.error


@pytest.mark.asyncio
async def test_transient_error_retries_then_succeeds(monkeypatch):
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(loop_mod.asyncio, "sleep", _no_sleep)

    loop = _loop([RuntimeError("blip"), [_delta("ok"), _done()]])
    resp = await loop.run_task("go")
    assert resp.text == "ok"
    # Retry must NOT pollute the transcript — it's surfaced via on_tool_event.
    assert "[Retrying" not in resp.text


@pytest.mark.asyncio
async def test_retry_surfaced_via_callback_not_transcript(monkeypatch):
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(loop_mod.asyncio, "sleep", _no_sleep)

    events: list[tuple[str, str, dict]] = []
    loop = AgentLoop(
        FakeProvider([RuntimeError("blip"), [_delta("ok"), _done()]]),
        FakeToolServer(),
        on_tool_event=lambda kind, name, data: events.append((kind, name, data)),
    )
    resp = await loop.run_task("go")
    assert resp.text == "ok"
    assert any(kind == "retry" for kind, _, _ in events)
