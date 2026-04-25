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
