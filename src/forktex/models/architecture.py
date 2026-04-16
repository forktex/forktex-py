"""Compatibility re-export for architecture models.

Canonical ownership is now ``forktex.architecture.models``.
"""

from forktex.architecture.models import (
    Component,
    Container,
    Dependency,
    ExternalSystem,
    HealthCheck,
    Person,
    Port,
    Relationship,
    ServiceType,
    SoftwareSystem,
    TechCategory,
    Technology,
    Workspace,
)

__all__ = [
    "Technology",
    "Port",
    "Dependency",
    "HealthCheck",
    "Relationship",
    "Component",
    "Container",
    "SoftwareSystem",
    "ExternalSystem",
    "Person",
    "Workspace",
    "ServiceType",
    "TechCategory",
]
