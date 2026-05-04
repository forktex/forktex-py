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

"""Client-side agent loop for the Intelligence API.

The Intelligence API is stateless — it receives messages + tool schemas
and returns text or tool_call responses. This module manages:

1. Conversation history (client-side)
2. Tool schema registration (from local ToolServer)
3. The tool-use loop: chat → tool_calls → execute → append results → chat again
4. Streaming with tool interception

The loop continues until the model produces a text response with no tool calls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, Optional

from forktex_intelligence.client.client import ForktexIntelligenceClient
from forktex_intelligence.streams import SSEEvent, SSEEventType, parse_sse_stream


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
    """Client-side conversation history for the stateless Intelligence API."""

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


class LocalAgentLoop:
    """Drives the agentic tool-use loop between the Intelligence API and local tools.

    Architecture:
    - The Intelligence API is stateless (no sessions)
    - This loop manages conversation history client-side
    - Tool schemas are sent with each request so the LLM knows what's available
    - When the LLM requests tool calls, they are executed locally
    - Results are appended to history and the loop continues
    """

    def __init__(
        self,
        client: ForktexIntelligenceClient,
        tool_server: Any,  # forktex.agent.intelligence.tool_server.ToolServer
        *,
        system: Optional[str] = None,
        on_tool_event: ToolEventCallback = None,
        max_tool_rounds: int = 20,
    ) -> None:
        self._client = client
        self._tool_server = tool_server
        self._on_tool_event = on_tool_event
        self._max_tool_rounds = max_tool_rounds
        self.conversation = Conversation(system=system)

    def _get_tool_schemas(self) -> list[Dict[str, Any]]:
        """Get tool schemas from the local tool server."""
        return self._tool_server.get_schemas()

    async def chat_stream(self, content: str) -> AsyncIterator[SSEEvent]:
        """Send a message and stream the response, handling tool-use loops.

        Yields SSEEvent objects for display. When the model requests tool calls,
        they are executed transparently and the conversation continues until
        the model produces a final text response.
        """
        self.conversation.add_user(content)
        tool_schemas = self._get_tool_schemas()

        for _round in range(self._max_tool_rounds):
            # Stream the response with retry on transient errors
            collected_text = ""
            collected_tool_calls: list[Dict[str, Any]] = []
            stream_ok = False

            for _attempt in range(3):
                try:
                    raw_stream = self._client.chat_stream(
                        self.conversation.messages,
                        system=self.conversation.system,
                        tools=tool_schemas if tool_schemas else None,
                    )

                    async for event in parse_sse_stream(raw_stream):
                        if event.event == SSEEventType.DELTA:
                            collected_text += event.delta_text
                            yield event
                        elif event.event == SSEEventType.TOOL_CALL:
                            collected_tool_calls.append(event.data)
                            yield event
                        elif event.event == SSEEventType.USAGE:
                            yield event
                        elif event.event == SSEEventType.ERROR:
                            yield event
                            return
                        elif event.event == SSEEventType.DONE:
                            yield event
                            break

                    stream_ok = True
                    break
                except Exception:
                    if _attempt < 2:
                        wait = (2**_attempt) * 5  # 5s, 10s
                        yield SSEEvent(
                            event=SSEEventType.DELTA,
                            data={"text": f"\n[Retrying in {wait}s...]\n"},
                        )
                        await asyncio.sleep(wait)
                        collected_text = ""
                        collected_tool_calls = []
                    else:
                        raise

            if not stream_ok:
                return

            # If no tool calls, we're done — record the assistant response
            if not collected_tool_calls:
                if collected_text:
                    self.conversation.add_assistant(collected_text)
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

        # Hit max rounds
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={
                "message": f"Agent loop exceeded {self._max_tool_rounds} tool rounds"
            },
        )

    async def run_task(self, task: str) -> AgentResponse:
        """Execute a task through the full agent loop, accumulating the response."""
        response = AgentResponse()

        async for event in self.chat_stream(task):
            if event.event == SSEEventType.DELTA:
                response.text += event.delta_text
            elif event.event == SSEEventType.TOOL_CALL:
                response.tool_calls_made.append(event.data)
            elif event.event == SSEEventType.USAGE:
                response.input_tokens += event.input_tokens
                response.output_tokens += event.output_tokens
            elif event.event == SSEEventType.ERROR:
                response.error = event.error_message

        return response
