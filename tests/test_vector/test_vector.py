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

from forktex.vector import CollectionHandle
from collections.abc import AsyncIterator
import uuid

import pytest
import pytest_asyncio

pytest.importorskip("qdrant_client", reason="qdrant-client not installed")

from forktex.vector import (
    ClientNotRegisteredError,
    SearchQuery,
    SparseVector,
    Vector,
    VectorPoint,
    deregister,
    get_client,
    register,
)
from forktex.error import AppErrorCode
from forktex.vector.errors import DimensionMismatchError, InvalidQueryError

DIM = 4
COLLECTION_PREFIX = "test-core-py--"


@pytest_asyncio.fixture
async def vector(qdrant_url: str) -> Vector:
    return Vector(qdrant_url=qdrant_url)


@pytest_asyncio.fixture
async def collection_name() -> str:
    return f"{COLLECTION_PREFIX}{uuid.uuid7().hex}"


@pytest_asyncio.fixture
async def coll(vector: Vector, collection_name: str) -> AsyncIterator[CollectionHandle]:
    handle = vector.collection(collection_name)
    await handle.create(dim=DIM, distance="cosine")
    yield handle
    try:
        await handle.delete()
    except Exception:
        pass


def _vec(vals: list[float]) -> list[float]:
    return (vals + [0.0] * DIM)[:DIM]


@pytest.mark.asyncio
async def test_create_and_info(coll: CollectionHandle) -> None:
    info = await coll.info()
    assert info.dim == DIM


@pytest.mark.asyncio
async def test_upsert_and_search_dense(coll: CollectionHandle) -> None:
    points = [
        VectorPoint(id=1, vector=_vec([1, 0, 0, 0]), payload={"text": "apple"}),
        VectorPoint(id=2, vector=_vec([0, 1, 0, 0]), payload={"text": "banana"}),
        VectorPoint(id=3, vector=_vec([0, 0, 1, 0]), payload={"text": "cherry"}),
    ]
    await coll.upsert(points)
    hits = await coll.search(SearchQuery(vector=_vec([1, 0, 0, 0])).limit(3))
    assert len(hits) > 0
    assert hits[0].id == 1


@pytest.mark.asyncio
async def test_upsert_with_uuid_ids(coll: CollectionHandle) -> None:
    uid = str(uuid.uuid7())
    await coll.upsert([VectorPoint(id=uid, vector=_vec([1, 0, 0, 0]))])
    hits = await coll.search(SearchQuery(vector=_vec([1, 0, 0, 0])).limit(1))
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_delete_points(coll: CollectionHandle) -> None:
    await coll.upsert([VectorPoint(id=100, vector=_vec([0.5, 0.5, 0, 0]))])
    await coll.delete_points([100])
    hits = await coll.search(SearchQuery(vector=_vec([0.5, 0.5, 0, 0])).limit(5))
    assert all(h.id != 100 for h in hits)


@pytest.mark.asyncio
async def test_score_threshold_filters(coll: CollectionHandle) -> None:
    await coll.upsert(
        [
            VectorPoint(id=10, vector=_vec([1, 0, 0, 0])),
            VectorPoint(id=11, vector=_vec([0, 0, 0, 1])),
        ]
    )
    hits = await coll.search(SearchQuery(vector=_vec([1, 0, 0, 0])).limit(10).score_threshold(0.9))
    ids = [h.id for h in hits]
    assert 10 in ids
    assert 11 not in ids


@pytest.mark.asyncio
async def test_payload_stored_and_returned(coll: CollectionHandle) -> None:
    await coll.upsert([VectorPoint(id=20, vector=_vec([1, 0, 0, 0]), payload={"key": "value", "n": 42})])
    hits = await coll.search(SearchQuery(vector=_vec([1, 0, 0, 0])).limit(1))
    assert len(hits) == 1
    assert hits[0].payload.get("key") == "value"
    assert hits[0].payload.get("n") == 42


@pytest.mark.asyncio
async def test_list_collections(vector: Vector, collection_name: str, coll: CollectionHandle) -> None:
    names = await vector.list_collections()
    assert collection_name in names


@pytest.mark.asyncio
async def test_list_collections_with_prefix(vector: Vector, collection_name: str, coll: CollectionHandle) -> None:
    names = await vector.list_collections(prefix=COLLECTION_PREFIX)
    assert all(n.startswith(COLLECTION_PREFIX) for n in names)
    assert collection_name in names


@pytest.mark.asyncio
async def test_search_across(vector: Vector) -> None:
    names = []
    for i in range(2):
        name = f"{COLLECTION_PREFIX}cross--{uuid.uuid7().hex}"
        h = vector.collection(name)
        await h.create(dim=DIM)
        await h.upsert([VectorPoint(id=i + 1, vector=_vec([float(i + 1), 0, 0, 0]), payload={"i": i})])
        names.append(name)
    try:
        hits = await vector.search_across(names, SearchQuery(vector=_vec([1, 0, 0, 0])).limit(4))
        assert len(hits) >= 1
        assert all(h.collection in names for h in hits)
        for h in hits:
            i = names.index(h.collection)
            assert h.payload == {"i": i}
    finally:
        for n in names:
            try:
                await vector.collection(n).delete()
            except Exception:
                pass


@pytest.mark.asyncio
async def test_rerank_returns_top_k(coll: CollectionHandle) -> None:
    points = [VectorPoint(id=i + 1, vector=_vec([float(i + 1), 0, 0, 0])) for i in range(5)]
    await coll.upsert(points)
    query_vec = _vec([5, 0, 0, 0])
    initial = await coll.search(SearchQuery(vector=query_vec).limit(5))
    reranked = await coll.rerank(query_vec, initial, top_k=3)
    assert len(reranked) <= 3
    assert reranked[0].score >= reranked[-1].score


@pytest.mark.asyncio
async def test_multimodal_collection(vector: Vector) -> None:
    name = f"{COLLECTION_PREFIX}mm--{uuid.uuid7().hex}"
    h = vector.collection(name)
    await h.create(dim=DIM, multimodal_dim=DIM)
    try:
        await h.upsert(
            [
                VectorPoint(
                    id=1,
                    vector=_vec([1, 0, 0, 0]),
                    multimodal_vector=_vec([0, 1, 0, 0]),
                )
            ]
        )
        hits = await h.search(SearchQuery(vector=_vec([0, 1, 0, 0])).using("multimodal").limit(1))
        assert len(hits) >= 1
    finally:
        await h.delete()


@pytest.mark.asyncio
async def test_sparse_vector_upsert_and_hybrid_search(vector: Vector) -> None:
    name = f"{COLLECTION_PREFIX}sparse--{uuid.uuid7().hex}"
    h = vector.collection(name)
    await h.create(dim=DIM, sparse=True)
    try:
        await h.upsert(
            [
                VectorPoint(
                    id=1,
                    vector=_vec([1, 0, 0, 0]),
                    payload={"text": "apple"},
                    sparse_vector=SparseVector(indices=[1, 3], values=[0.5, 0.8]),
                ),
                VectorPoint(id=2, vector=_vec([0, 1, 0, 0]), payload={"text": "banana"}),
            ]
        )
        info = await h.info()
        assert info.has_sparse is True

        hits = await h.search(SearchQuery(vector=_vec([1, 0, 0, 0])).using("hybrid").limit(5))
        assert len(hits) >= 1
    finally:
        await h.delete()


@pytest.mark.asyncio
async def test_upsert_dimension_mismatch_raises_typed_error(coll: CollectionHandle) -> None:
    with pytest.raises(DimensionMismatchError):
        await coll.upsert([VectorPoint(id=1, vector=[1.0, 0.0])])


def test_register_get_client_deregister_roundtrip() -> None:
    try:
        registered = register("test-registry-client", qdrant_url="http://localhost:6333")
        assert get_client("test-registry-client") is registered
        dropped = deregister("test-registry-client")
        assert dropped is registered
        assert deregister("test-registry-client") is None
    finally:
        deregister("test-registry-client")


def test_get_client_unregistered_raises() -> None:
    with pytest.raises(ClientNotRegisteredError):
        get_client("definitely-not-registered")


@pytest.mark.asyncio
async def test_sparse_strategy_searches_the_sparse_space_not_the_dense_one(vector: Vector) -> None:
    name = f"{COLLECTION_PREFIX}sparse-only--{uuid.uuid7().hex}"
    h = vector.collection(name)
    await h.create(dim=DIM, sparse=True)
    try:
        await h.upsert(
            [
                VectorPoint(
                    id=1,
                    vector=_vec([0, 0, 0, 1]),
                    payload={"text": "keyword-match"},
                    sparse_vector=SparseVector(indices=[7, 9], values=[0.9, 0.8]),
                ),
                VectorPoint(
                    id=2,
                    vector=_vec([1, 0, 0, 0]),
                    payload={"text": "dense-match"},
                    sparse_vector=SparseVector(indices=[42], values=[0.1]),
                ),
            ]
        )

        hits = await h.search(
            SearchQuery(vector=_vec([1, 0, 0, 0]))
            .using("sparse")
            .sparse(SparseVector(indices=[7, 9], values=[1.0, 1.0]))
            .limit(5)
        )

        assert hits, "sparse search returned nothing"
        assert hits[0].id == 1, f"sparse search ranked by the dense vector: {[h_.id for h_ in hits]}"
    finally:
        await h.delete()


@pytest.mark.asyncio
async def test_sparse_strategy_without_a_sparse_vector_is_rejected(coll: CollectionHandle) -> None:
    with pytest.raises(InvalidQueryError, match="requires a sparse query vector"):
        await coll.search(SearchQuery(vector=_vec([1, 0, 0, 0])).using("sparse"))


@pytest.mark.asyncio
async def test_unknown_strategy_is_a_bad_request_not_an_internal_error(coll: CollectionHandle) -> None:
    query = SearchQuery(vector=_vec([1, 0, 0, 0]))
    query._strategy = "nonsense"
    with pytest.raises(InvalidQueryError) as excinfo:
        await coll.search(query)
    assert excinfo.value.code == AppErrorCode.BAD_REQUEST
