"""Shared building blocks for per-facet credential management.

The three facets (cloud, intelligence, network) each register their own
``login`` / ``logout`` commands built by
:func:`forktex.agent.auth.cli.build_facet_commands`. There is no standalone
``forktex auth`` group — the verbs live inside each facet for full parity.

The top-level ``forktex status`` aggregator also lives here.
"""

from __future__ import annotations

from forktex.agent.auth.cli import (
    build_facet_commands,
    login_cloud,
    login_intelligence,
    login_network,
    status_cmd,
)
from forktex.agent.auth.status import collect_auth_status
from forktex.agent.auth.types import AuthKind, AuthState, Facet

__all__ = [
    "build_facet_commands",
    "status_cmd",
    "login_cloud",
    "login_intelligence",
    "login_network",
    "collect_auth_status",
    "AuthState",
    "Facet",
    "AuthKind",
]
