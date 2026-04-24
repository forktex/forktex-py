"""Shared types for the unified auth surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

Facet = Literal["cloud", "intelligence", "network"]
AuthKind = Literal["api_key", "jwt", "personal_token"]
Scope = Literal["global", "project"]

FACETS: tuple[Facet, ...] = ("cloud", "intelligence", "network")


@dataclass
class AuthState:
    """Observed state of one facet's credentials on disk.

    ``configured`` is True iff a credential file exists and parses. ``reachable``
    is filled in by the status pinger when ``configured``; left as ``None`` if
    we didn't probe. ``detail`` carries facet-specific key/value extras
    surfaced in ``auth status`` (e.g. intelligence model name, cloud org slug).
    """

    facet: Facet
    configured: bool
    endpoint: Optional[str] = None
    principal: Optional[str] = None
    auth_kind: Optional[AuthKind] = None
    scope: Optional[Scope] = None
    source_path: Optional[Path] = None
    reachable: Optional[bool] = None
    error: Optional[str] = None
    detail: dict[str, str] = field(default_factory=dict)
