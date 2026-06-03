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

"""The agentic loop — provider-agnostic ReAct over a tool server.

The loop owns conversation history client-side, sends tool schemas with each
turn, executes requested tool calls locally, and continues until the model
produces a final text response. It depends only on the ``LLMProvider`` port
(``provider.py``) and a duck-typed tool server (``get_schemas()`` + ``call()``)
— never on a concrete LLM SDK or the tool implementations.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, Optional

from forktex.agent.engine.events import AgentEvent, AgentEventType
from forktex.agent.engine.provider import LLMProvider
from forktex.agent.engine.retry import AgentLoopExhausted, RetryPolicy


@dataclass
class AgentResponse:
    """Accumulated response from an agent run."""

    text: str = ""
    tool_calls_made: list[Dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None


# Type alias for the tool event callback
ToolEventCallback = Optional[Callable[[str, str, Dict[str, Any]], None]]


class Conversation:
    """Client-side conversation history for a stateless chat backend."""

    def __init__(self, *, system: Optional[str] = None) -> None:
        self.system = system
        self.messages: list[Dict[str, str]] = []

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_result(self, tool_call_id: str, tool_name: str, content: str) -> None:
        """Add tool result as a tool-role message for the next turn."""
        self.messages.append(
            {
                "role": "tool",
                "content": content,
                "tool_call_id": tool_call_id,
            }
        )

    def add_assistant_tool_calls(
        self, text: str, tool_calls: list[Dict[str, Any]]
    ) -> None:
        """Record that the assistant requested tool calls.

        Includes the structured tool_calls so the server can reconstruct
        the proper wire format for the underlying model.
        """
        self.messages.append(
            {
                "role": "assistant",
                "content": text or "",
                "tool_calls": tool_calls,
            }
        )

    def clear(self) -> None:
        self.messages.clear()


class AgentLoop:
    """Drives the agentic tool-use loop between an ``LLMProvider`` and local tools.

    - The provider is stateless; this loop manages conversation history.
    - Tool schemas are sent with each request so the model knows what's available.
    - When the model requests tool calls, they are executed locally and their
      results appended to history; the loop continues until a final text turn.
    """

    def __init__(
        self,
        provider: LLMProvider,
        tool_server: Any,  # duck-typed: get_schemas() + async call()
        *,
        system: Optional[str] = None,
        on_tool_event: ToolEventCallback = None,
        max_tool_rounds: int = 20,
        retry: Optional[RetryPolicy] = None,
    ) -> None:
        self._provider = provider
        self._tool_server = tool_server
        self._on_tool_event = on_tool_event
        self._max_tool_rounds = max_tool_rounds
        self._retry = retry or RetryPolicy()
        self.conversation = Conversation(system=system)

    def _get_tool_schemas(self) -> list[Dict[str, Any]]:
        """Get tool schemas from the local tool server."""
        return self._tool_server.get_schemas()

    async def chat_stream(self, content: str) -> AsyncIterator[AgentEvent]:
        """Send a message and stream the response, handling tool-use loops.

        Yields ``AgentEvent`` objects for display. When the model requests tool
        calls, they are executed transparently and the conversation continues
        until the model produces a final text response.
        """
        self.conversation.add_user(content)
        tool_schemas = self._get_tool_schemas()

        for _round in range(self._max_tool_rounds):
            # Stream the response with retry on transient errors
            collected_text = ""
            collected_tool_calls: list[Dict[str, Any]] = []
            stream_ok = False

            for _attempt in range(self._retry.max_attempts):
                try:
                    async for event in self._provider.chat_stream(
                        self.conversation.messages,
                        system=self.conversation.system,
                        tools=tool_schemas if tool_schemas else None,
                    ):
                        if event.event == AgentEventType.DELTA:
                            collected_text += event.delta_text
                            yield event
                        elif event.event == AgentEventType.TOOL_CALL:
                            collected_tool_calls.append(event.data)
                            yield event
                        elif event.event == AgentEventType.USAGE:
                            yield event
                        elif event.event == AgentEventType.ERROR:
                            yield event
                            return
                        elif event.event == AgentEventType.DONE:
                            yield event
                            break

                    stream_ok = True
                    break
                except self._retry.transient:
                    if self._retry.is_last(_attempt):
                        raise
                    # Surface the retry to the UI via the callback — never the
                    # transcript — then back off and start the turn over.
                    delay = self._retry.delay_for(_attempt)
                    if self._on_tool_event:
                        self._on_tool_event(
                            "retry", "", {"attempt": _attempt + 1, "delay": delay}
                        )
                    await asyncio.sleep(delay)
                    collected_text = ""
                    collected_tool_calls = []

            if not stream_ok:
                return

            # If no tool calls, we're done — record the assistant response
            if not collected_tool_calls:
                if collected_text:
                    self.conversation.add_assistant(collected_text)
                    return
                # No text and no tool calls — the provider returned an empty
                # response (an incapable model, or a stream that errored after
                # opening). Surface it instead of finishing silently "completed".
                yield AgentEvent(
                    event=AgentEventType.ERROR,
                    data={
                        "message": "the model returned an empty response — "
                        "check the configured model/endpoint"
                    },
                )
                return

            # Tool calls requested — execute them and loop
            self.conversation.add_assistant_tool_calls(
                collected_text, collected_tool_calls
            )

            for tc in collected_tool_calls:
                tool_name = tc.get("name", "")
                call_id = tc.get("id", "")
                arguments = tc.get("arguments", {})

                if self._on_tool_event:
                    self._on_tool_event("call", tool_name, arguments)

                # Execute tool locally
                result = await self._tool_server.call(tool_name, **arguments)

                if self._on_tool_event:
                    self._on_tool_event("result", tool_name, result.to_dict())

                # Add result to conversation for next turn
                self.conversation.add_tool_result(call_id, tool_name, result.content)

        # Hit max rounds — a terminal failure, raised (not a transcript event).
        raise AgentLoopExhausted(
            f"Agent loop exceeded {self._max_tool_rounds} tool rounds"
        )

    async def run_task(self, task: str) -> AgentResponse:
        """Execute a task through the full agent loop, accumulating the response."""
        response = AgentResponse()

        try:
            async for event in self.chat_stream(task):
                if event.event == AgentEventType.DELTA:
                    response.text += event.delta_text
                elif event.event == AgentEventType.TOOL_CALL:
                    response.tool_calls_made.append(event.data)
                elif event.event == AgentEventType.USAGE:
                    response.input_tokens += event.input_tokens
                    response.output_tokens += event.output_tokens
                elif event.event == AgentEventType.ERROR:
                    response.error = event.error_message
        except AgentLoopExhausted as exc:
            response.error = str(exc)

        return response


__all__ = ["AgentLoop", "AgentResponse", "Conversation", "ToolEventCallback"]
