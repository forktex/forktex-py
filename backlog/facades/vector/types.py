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


from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from forktex.types import BaseValueObject

SearchStrategy = Literal["dense", "multimodal", "hybrid", "sparse"]


class SparseVector(BaseValueObject):
    indices: list[int]
    values: list[float]


class VectorPoint(BaseValueObject):
    id: str | int
    vector: list[float]
    payload: dict[str, Any] = Field(default_factory=dict)
    multimodal_vector: list[float] | None = None
    sparse_vector: SparseVector | None = None


class SearchHit(BaseValueObject):
    id: str | int
    score: float
    payload: dict[str, Any]
    collection: str | None = None


class CollectionInfo(BaseValueObject):
    name: str
    vectors_count: int
    dim: int
    multimodal_dim: int | None = None
    has_sparse: bool = False
    distance: str = "cosine"


class SearchQuery:
    def __init__(self, vector: list[float]) -> None:
        self._vector = vector
        self._multimodal_vector: list[float] | None = None
        self._sparse_vector: SparseVector | None = None
        self._limit: int = 10
        self._strategy: SearchStrategy = "dense"
        self._payload_filter: dict[str, Any] | None = None
        self._score_threshold: float | None = None

    def limit(self, k: int) -> SearchQuery:
        self._limit = k
        return self

    def using(self, strategy: SearchStrategy) -> SearchQuery:
        self._strategy = strategy
        return self

    def multimodal(self, vector: list[float]) -> SearchQuery:
        self._multimodal_vector = vector
        return self

    def sparse(self, vector: SparseVector) -> SearchQuery:
        self._sparse_vector = vector
        return self

    def filter(self, payload_filter: dict[str, Any]) -> SearchQuery:
        self._payload_filter = payload_filter
        return self

    def score_threshold(self, threshold: float) -> SearchQuery:
        self._score_threshold = threshold
        return self


__all__ = [
    "CollectionInfo",
    "SearchHit",
    "SearchQuery",
    "SearchStrategy",
    "SparseVector",
    "VectorPoint",
]
