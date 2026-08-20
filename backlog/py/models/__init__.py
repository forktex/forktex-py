# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Compatibility facade for domain-owned model packages."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from forktex.models.base import ForkTexModel, Identifiable, Versioned, Tagged

if TYPE_CHECKING:
    # Static visibility for the lazily-exported names (runtime path is the
    # ``__getattr__`` below). Lets type-checkers resolve ``from forktex.models
    # import <Name>`` and satisfy ``__all__`` without importing the heavy
    # submodules at runtime.
    from forktex.architecture.models import (
        Component,
        Container,
        Dependency,
        HealthCheck,
        Port,
        ServiceType,
        SoftwareSystem,
        TechCategory,
        Technology,
        Workspace,
    )
    from forktex.engineering.models import (
        Archetype,
        Blueprint,
        DeliveryStandard,
        TechItem,
    )
    from forktex.fsd.models import (
        Atom,
        Domain,
        FacetAtomRef,
        Facet,
        FSDAtom,
        FSDDomain,
        FSDLevel,
        FSDProfile,
        FSDProfileAtomPolicy,
        FSDProjectAtomOverride,
        FSDProjectConfig,
        FSDStandard,
        FSDStandardV1,
        ISORef,
        Level,
        ResolveRule,
    )
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
        ServiceDef,
        SSLConfig,
    )


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


# Static public surface (mirrors the lazy ``_EXPORTS`` keys above). Kept literal
# so type-checkers can resolve ``from forktex.models import *`` without evaluating
# the dict; a test asserts this list stays in sync with ``_EXPORTS``.
__all__ = [
    "ForkTexModel",
    "Identifiable",
    "Versioned",
    "Tagged",
    # fsd
    "ISORef",
    "ResolveRule",
    "Domain",
    "Atom",
    "FacetAtomRef",
    "Facet",
    "Level",
    "FSDStandard",
    "FSDAtom",
    "FSDDomain",
    "FSDLevel",
    "FSDStandardV1",
    "FSDProfileAtomPolicy",
    "FSDProfile",
    "FSDProjectAtomOverride",
    "FSDProjectConfig",
    # architecture
    "Technology",
    "Port",
    "Dependency",
    "HealthCheck",
    "Component",
    "Container",
    "SoftwareSystem",
    "Workspace",
    "ServiceType",
    "TechCategory",
    # engineering
    "TechItem",
    "Archetype",
    "Blueprint",
    "DeliveryStandard",
    # manifest
    "ForktexManifest",
    "FSDConfig",
    "AtomOverride",
    "ServiceDef",
    "PackageDef",
    "MetadataDef",
    "InfrastructureDef",
    "DeploymentDef",
    "GatewayDef",
    "ObservabilityDef",
    "GatewayDomain",
    "SSLConfig",
]
