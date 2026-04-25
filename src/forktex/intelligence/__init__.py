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

"""forktex.intelligence — Re-exports from the standalone forktex_intelligence SDK.

For standalone usage, install forktex-intelligence directly:
    pip install forktex-intelligence
    from forktex_intelligence import Intelligence

Within the forktex CLI, both import paths work:
    from forktex.intelligence import Intelligence
    from forktex_intelligence import Intelligence
"""

from forktex_intelligence.api import (
    AvailableModel,
    Intelligence,
    Response,
    StructuredResponse,
    StreamChunks,
)
from forktex_intelligence.config import IntelligenceSettings
from forktex.agent.intelligence.settings import (
    get_intelligence_settings,
    reset_intelligence_settings,
)
from forktex_intelligence.client.client import (
    ForktexIntelligenceClient,
    IntelligenceAPIError,
)
from forktex_intelligence.client.generated import (
    ChatMessage,
    ChatResponse,
    HealthResponse,
    StructuredChatResponse,
    ToolCallInfo,
    UsageInfo,
)
from forktex_intelligence.streams import SSEEvent, SSEEventType

__all__ = [
    # High-level API
    "AvailableModel",
    "Intelligence",
    "Response",
    "StructuredResponse",
    "StreamChunks",
    # Configuration
    "IntelligenceSettings",
    "get_intelligence_settings",
    "reset_intelligence_settings",
    # Low-level client (advanced)
    "ForktexIntelligenceClient",
    "IntelligenceAPIError",
    # Wire-level models (advanced — prefer high-level API)
    "ChatMessage",
    "ChatResponse",
    "HealthResponse",
    "StructuredChatResponse",
    "ToolCallInfo",
    "UsageInfo",
    # Streaming
    "SSEEvent",
    "SSEEventType",
]
