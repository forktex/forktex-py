"""Compatibility facade for domain-owned model packages."""

from __future__ import annotations

from importlib import import_module

from forktex.models.base import ForkTexModel, Identifiable, Versioned, Tagged


_EXPORTS = {
    # fsd
    "ISORef": "forktex.fsd.models",
    "ResolveRule": "forktex.fsd.models",
    "Domain": "forktex.fsd.models",
    "Atom": "forktex.fsd.models",
    "FacetAtomRef": "forktex.fsd.models",
    "Facet": "forktex.fsd.models",
    "Level": "forktex.fsd.models",
    "FSDStandard": "forktex.fsd.models",
    "FSDAtom": "forktex.fsd.models",
    "FSDDomain": "forktex.fsd.models",
    "FSDLevel": "forktex.fsd.models",
    "FSDStandardV1": "forktex.fsd.models",
    "FSDProfileAtomPolicy": "forktex.fsd.models",
    "FSDProfile": "forktex.fsd.models",
    "FSDProjectAtomOverride": "forktex.fsd.models",
    "FSDProjectConfig": "forktex.fsd.models",
    # architecture
    "Technology": "forktex.architecture.models",
    "Port": "forktex.architecture.models",
    "Dependency": "forktex.architecture.models",
    "HealthCheck": "forktex.architecture.models",
    "Component": "forktex.architecture.models",
    "Container": "forktex.architecture.models",
    "SoftwareSystem": "forktex.architecture.models",
    "Workspace": "forktex.architecture.models",
    "ServiceType": "forktex.architecture.models",
    "TechCategory": "forktex.architecture.models",
    # engineering
    "TechItem": "forktex.engineering.models",
    "Archetype": "forktex.engineering.models",
    "Blueprint": "forktex.engineering.models",
    "DeliveryStandard": "forktex.engineering.models",
    # manifest
    "ForktexManifest": "forktex.manifest.models",
    "FSDConfig": "forktex.manifest.models",
    "AtomOverride": "forktex.manifest.models",
    "ServiceDef": "forktex.manifest.models",
    "PackageDef": "forktex.manifest.models",
    "MetadataDef": "forktex.manifest.models",
    "InfrastructureDef": "forktex.manifest.models",
    "DeploymentDef": "forktex.manifest.models",
    "GatewayDef": "forktex.manifest.models",
    "ObservabilityDef": "forktex.manifest.models",
    "GatewayDomain": "forktex.manifest.models",
    "SSLConfig": "forktex.manifest.models",
}


def __getattr__(name: str):
    if name in _EXPORTS:
        module = import_module(_EXPORTS[name])
        return getattr(module, name)
    raise AttributeError(name)


__all__ = [
    "ForkTexModel",
    "Identifiable",
    "Versioned",
    "Tagged",
    *_EXPORTS.keys(),
]
