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

"""The LLM provider port — the engine's one seam to a model backend.

``AgentLoop`` depends only on this Protocol, never on a concrete SDK. The
adapter lives in ``agent/intelligence/provider.py`` (wraps
``forktex_intelligence.Intelligence``); swapping backends means writing another
adapter, not touching the loop.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, runtime_checkable

from forktex.agent.engine.events import AgentEvent


@runtime_checkable
class LLMProvider(Protocol):
    """A streaming chat backend.

    ``chat_stream`` returns an async iterator of **already-parsed**
    ``AgentEvent``s (DELTA / TOOL_CALL / USAGE / ERROR / DONE). It is a plain
    method returning an iterator (not a coroutine), so the loop can
    ``async for event in provider.chat_stream(...)`` and re-open the stream on
    retry without re-awaiting.
    """

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[AgentEvent]: ...


__all__ = ["LLMProvider"]
