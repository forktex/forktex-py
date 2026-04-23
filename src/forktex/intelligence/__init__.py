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
