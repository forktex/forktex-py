"""Engineering domain models."""

from __future__ import annotations

from pydantic import computed_field

from forktex.models.base import ForkTexModel, Identifiable, Versioned


class TechItem(ForkTexModel):
    """A technology component with name and version."""

    name: str
    version: str = ""
    role: str = ""


class Archetype(Identifiable, Versioned):
    """Technology-generic blueprint for a component type."""

    slug: str
    stack: list[str] = []
    tech_stack: list[TechItem] = []
    features: list[str] = []
    fsd_atoms: list[str] = []
    colors: dict[str, str] = {}

    @computed_field
    @property
    def primary_tech(self) -> str:
        return self.stack[0] if self.stack else ""


class Blueprint(Identifiable, Versioned):
    """Platform-specific development knowledge."""

    slug: str
    platform: str = ""
    archetype: str = ""
    stack: list[str] = []
    engines: list[dict] = []
    routes: list[dict] = []
    models: list[dict] = []
    patterns: list[str] = []


class DeliveryStandard(Identifiable, Versioned):
    """A delivery convention that all platforms follow."""

    slug: str
    path: str = ""
