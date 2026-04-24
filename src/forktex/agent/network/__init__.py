"""forktex.agent.network — Network facet (forktex-network SDK integration).

Exposes a ``forktex network`` CLI group (status-only in V1) and a thin
settings layer mirroring the cloud/intelligence pattern.
"""

from __future__ import annotations

from forktex.agent.network.cli import network
from forktex.agent.network.settings import (
    NetworkSettings,
    load_network_settings,
    save_network_global,
    save_network_project,
)

__all__ = [
    "network",
    "NetworkSettings",
    "load_network_settings",
    "save_network_global",
    "save_network_project",
]
