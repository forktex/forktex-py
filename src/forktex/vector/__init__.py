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


from forktex.registry import ClientRegistry
from forktex.vector.collection import CollectionHandle
from forktex.vector.errors import (
    ClientNotRegisteredError,
    CollectionNotFoundError,
    DimensionMismatchError,
    VectorError,
)
from forktex.vector.types import (
    CollectionInfo,
    SearchHit,
    SearchQuery,
    SearchStrategy,
    SparseVector,
    VectorPoint,
)
from forktex.vector.vector import Vector

_registry: ClientRegistry[Vector] = ClientRegistry("vector", ClientNotRegisteredError)


def register(name: str, qdrant_url: str, *, api_key: str | None = None) -> Vector:
    return _registry.set(name, Vector(qdrant_url=qdrant_url, api_key=api_key))


def get_client(name: str = "default") -> Vector:
    return _registry.get(name)


def deregister(name: str = "default") -> Vector | None:
    return _registry.pop(name)


__all__ = [
    "ClientNotRegisteredError",
    "CollectionHandle",
    "CollectionInfo",
    "CollectionNotFoundError",
    "DimensionMismatchError",
    "SearchHit",
    "SearchQuery",
    "SearchStrategy",
    "SparseVector",
    "Vector",
    "VectorError",
    "VectorPoint",
    "deregister",
    "get_client",
    "register",
]
