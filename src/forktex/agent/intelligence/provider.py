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

"""ForkTex Intelligence adapter for the engine ``LLMProvider`` port.

Wraps ``forktex_intelligence.Intelligence`` and owns the one internal SDK
touchpoint — ``parse_sse_stream`` — so the engine loop never imports the SDK.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

from forktex_intelligence import Intelligence

# parse_sse_stream is not on the SDK's top-level surface; it's the one
# documented internal touchpoint until the SDK lifts it. It is confined here.
from forktex_intelligence.streams import parse_sse_stream

from forktex.agent.engine.events import AgentEvent


class IntelligenceProvider:
    """Adapts ``Intelligence`` to the engine ``LLMProvider`` port."""

    def __init__(self, client: Intelligence) -> None:
        self._client = client

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Open a streamed turn and yield already-parsed ``AgentEvent``s."""
        return parse_sse_stream(
            self._client.chat_stream(messages, system=system, tools=tools)
        )


__all__ = ["IntelligenceProvider"]
