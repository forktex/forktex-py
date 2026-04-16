"""Compatibility re-export for manifest models.

Canonical ownership is now ``forktex.manifest.models``.
"""

from forktex.manifest.models import (
    AtomOverride,
    DeploymentDef,
    FSDConfig,
    ForktexManifest,
    GatewayDef,
    GatewayDomain,
    InfrastructureDef,
    MetadataDef,
    ObservabilityDef,
    PackageDef,
    SSLConfig,
    ServiceDef,
)

__all__ = [
    "AtomOverride",
    "FSDConfig",
    "MetadataDef",
    "ServiceDef",
    "InfrastructureDef",
    "DeploymentDef",
    "GatewayDomain",
    "SSLConfig",
    "GatewayDef",
    "ObservabilityDef",
    "PackageDef",
    "ForktexManifest",
]
