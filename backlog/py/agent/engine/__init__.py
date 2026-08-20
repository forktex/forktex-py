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

"""The forktex agentic engine — the provider-agnostic agent domain.

One place for what "running an agent" means: the loop (``AgentLoop``) over an
``LLMProvider`` port and a tool server, conversation history, the process /
session / state / type lifecycle primitives, and the shared event vocabulary.

Dependency rule: the engine depends only on the substrate + the provider port —
never on a concrete LLM SDK, the tool implementations, or the CLI/UI. Provider
adapters (e.g. ``agent/intelligence/provider.py``) and the composition root
(``agent/manager.py``) depend on the engine, never the reverse.
"""

from forktex.agent.engine.events import AgentEvent, AgentEventType
from forktex.agent.engine.loop import (
    AgentLoop,
    AgentResponse,
    Conversation,
    ToolEventCallback,
)
from forktex.agent.engine.process import AgentProcess, AgentStatus
from forktex.agent.engine.provider import LLMProvider
from forktex.agent.engine.retry import AgentLoopExhausted, RetryPolicy
from forktex.agent.engine.session import Session
from forktex.agent.engine.state import AgentStateStore
from forktex.agent.engine.types import (
    AgentType,
    AgentTypeRegistry,
    get_agent_type_registry,
    reset_agent_type_registry,
    route_agent_type,
)

__all__ = [
    "AgentEvent",
    "AgentEventType",
    "AgentLoop",
    "AgentResponse",
    "Conversation",
    "ToolEventCallback",
    "LLMProvider",
    "RetryPolicy",
    "AgentLoopExhausted",
    "AgentProcess",
    "AgentStatus",
    "Session",
    "AgentStateStore",
    "AgentType",
    "AgentTypeRegistry",
    "get_agent_type_registry",
    "reset_agent_type_registry",
    "route_agent_type",
]
