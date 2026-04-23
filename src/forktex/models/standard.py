"""Compatibility re-export for FSD models.

Canonical ownership is now ``forktex.fsd.models``.
"""

from forktex.fsd.models import (
    Atom,
    Domain,
    FSDStandard,
    Facet,
    FacetAtomRef,
    ISORef,
    Level,
    ResolveRule,
)

__all__ = [
    "ISORef",
    "ResolveRule",
    "Domain",
    "Atom",
    "FacetAtomRef",
    "Facet",
    "Level",
    "FSDStandard",
]
