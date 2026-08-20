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

"""Multi-modal vector space embedding and search over Qdrant.

Qdrant-first with a thin abstraction layer that surfaces four search strategies:
dense (text), multimodal (CLIP/image), hybrid (dense+sparse RRF fusion),
and sparse (BM25/SPLADE keyword).

Collections are tenant-scoped by caller convention — the caller sets the
collection name (e.g. ``f"org-{org_id}--knowledge"``).

    vector = Vector(qdrant_url="http://qdrant:6333")

    # Create (idempotent)
    coll = vector.collection("org-abc:knowledge")
    await coll.create(dim=1536, multimodal_dim=512)

    # Upsert
    await coll.upsert([
        VectorPoint(
            id="chunk-001",
            vector=embed_text("The capital of France is Paris."),
            payload={"text": "The capital of France is Paris.", "source": "wiki"},
            multimodal_vector=embed_clip(image),  # optional
        )
    ])

    # Search — dense (default)
    hits = await coll.search(SearchQuery(vector=embed_text(query)).limit(10))

    # Search — hybrid
    hits = await coll.search(
        SearchQuery(vector=embed_text(query))
        .limit(10)
        .using("hybrid")
        .score_threshold(0.6)
    )

Requires: pip install 'forktex[vector]'  (qdrant-client)
"""

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

# Mirrors ``forktex.storage``'s registry: register a named ``Vector``
# at startup, look it up by name from anywhere (e.g., the rich VECTOR
# field handler in [space]). ``"default"`` is the convention for
# single-client setups.

_registry: ClientRegistry[Vector] = ClientRegistry("vector", ClientNotRegisteredError)


def register(name: str, qdrant_url: str, *, api_key: str | None = None) -> Vector:
    """Register a named ``Vector`` client and return it.

    Replaces any previous client of the same name. ``Vector`` builds a fresh
    ``AsyncQdrantClient`` per operation, so nothing is leaked by replacement.
    """
    return _registry.set(name, Vector(qdrant_url=qdrant_url, api_key=api_key))


def get_client(name: str = "default") -> Vector:
    """Return a registered ``Vector`` client by name.

    Raises ``ClientNotRegisteredError`` if the name has not been registered.
    """
    return _registry.get(name)


def deregister(name: str = "default") -> Vector | None:
    """Remove ``name`` from the registry and return the dropped client (or
    ``None`` if it wasn't registered). Idempotent."""
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
