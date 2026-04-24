"""Pluggable agent driver protocol — reserved for Intelligence SDK implementations.

Today we only use the HTTP driver (backed by ``ForktexIntelligenceClient``).
The protocol is defined here so a later local-model driver, shipped inside
``forktex_intelligence``, can plug into the root loop without changes to
``forktex-py``. This mirrors how ``forktex_cloud`` contributes non-HTTP code
(paths, manifest, bridge, scaffold) alongside its HTTP client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AgentResponse:
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


class AgentDriver(Protocol):
    """Minimal surface the root loop depends on.

    Implementations:
    - HTTP: ``forktex_intelligence.drivers.http.HttpAgentDriver`` (future home).
      Until the SDK exposes it, the root loop wires the chat REPL directly.
    - Local model: follow-up, entirely additive in ``forktex_intelligence``.
    """

    async def handle(self, user_input: str) -> AgentResponse:  # pragma: no cover
        ...
