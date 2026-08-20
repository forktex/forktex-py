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


"""``StoreConfig`` + ``StoreClient`` — the MongoDB client itself, plus the
``ObjectId``/``_id`` normalisation every method funnels through.

Split out of ``__init__.py`` so that module is the package *surface* (registry,
module-level facade, ``__all__``) — ``package-layout.md`` rule 1, one module per
concern.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from forktex.log import get_logger
from forktex.types import BaseValueObject

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pymongo.asynchronous.client_session import AsyncClientSession
    from pymongo.asynchronous.mongo_client import AsyncMongoClient

logger = get_logger(__name__)


class StoreConfig(BaseValueObject):
    url: str
    """MongoDB connection URI, e.g. ``mongodb://localhost:27017``."""
    database: str
    """Logical database name within the MongoDB deployment."""


def _make_client(url: str) -> AsyncMongoClient:
    try:
        from pymongo import AsyncMongoClient
    except ImportError as exc:
        raise ImportError("Install 'forktex[store]' (pymongo) to use forktex.store") from exc
    return AsyncMongoClient(url)


def _to_query_id(value: object) -> object:
    """Coerce a string that looks like a valid ``ObjectId`` back to one.

    Auto-generated ids are stored as real ``ObjectId``s (the ordinary,
    idiomatic MongoDB default) — a string filter would never match one (a
    string and an ``ObjectId`` are different BSON types even when they
    print the same), so lookups must convert back. Caller-supplied custom
    ids that don't look like a 24-hex-char ``ObjectId`` are left untouched,
    since they were stored as literal strings.

    Edge case this can't disambiguate: a caller-supplied custom id that
    happens to *also* be valid ``ObjectId`` hex form gets coerced here too,
    which would mismatch the literal string it was actually stored as. Rare
    in practice — avoid raw 24-hex-char custom ids if this matters.
    """
    from bson import ObjectId

    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return value


def _normalize_filter(filter: dict[str, Any]) -> dict[str, Any]:
    if "_id" in filter:
        filter = dict(filter)
        filter["_id"] = _to_query_id(filter["_id"])
    return filter


def _normalize(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert MongoDB's ``ObjectId`` ``_id`` to a plain string.

    Every document this module hands back has a string ``_id`` — matching
    the rest of the codebase's convention of string identifiers everywhere
    — instead of leaking a ``bson.ObjectId`` that isn't JSON-serializable
    by default.
    """
    if doc is None:
        return None
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


class StoreClient:
    """Async MongoDB client scoped to a single logical database.

    Obtained via ``register(name, ...)`` + ``get_client(name)``, or constructed
    directly with a ``StoreConfig``. Holds one persistent ``AsyncMongoClient``
    for its lifetime — unlike ``forktex.storage``'s per-call clients,
    MongoDB's async client is designed to be constructed once and reused; it
    manages its own internal connection pool.
    """

    def __init__(self, config: StoreConfig) -> None:
        self._config = config
        self._client = _make_client(config.url)
        self._db = self._client[config.database]

    async def insert_one(
        self,
        collection: str,
        document: dict[str, Any],
        *,
        id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> str:
        """Insert ``document`` into ``collection``. Returns the document id.

        Pass ``id`` to store a caller-supplied string id (e.g. a natural
        key); otherwise MongoDB assigns a real ``ObjectId`` (returned as
        its string form).
        """
        payload = dict(document)
        if id is not None:
            payload["_id"] = id
        result = await self._db[collection].insert_one(payload, session=session)
        return str(result.inserted_id)

    async def find_one(
        self,
        collection: str,
        filter: dict[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """Return the first document matching ``filter``, or ``None``."""
        doc = await self._db[collection].find_one(_normalize_filter(filter), session=session)
        return _normalize(doc)

    async def find(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
        *,
        limit: int = 100,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` documents matching ``filter`` (default: all)."""
        query = _normalize_filter(filter) if filter else {}
        cursor = self._db[collection].find(query, session=session).limit(limit)
        return [doc for doc in [_normalize(d) async for d in cursor] if doc is not None]

    async def update_one(
        self,
        collection: str,
        filter: dict[str, Any],
        update: dict[str, Any],
        *,
        upsert: bool = False,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """Set fields in ``update`` on the first document matching ``filter``.

        Returns ``True`` if a document was modified or (with ``upsert=True``)
        newly inserted.
        """
        result = await self._db[collection].update_one(
            _normalize_filter(filter), {"$set": update}, upsert=upsert, session=session
        )
        return result.modified_count > 0 or result.upserted_id is not None

    async def delete_one(
        self,
        collection: str,
        filter: dict[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """Delete the first document matching ``filter``. Returns ``True`` if
        a document was actually deleted."""
        result = await self._db[collection].delete_one(_normalize_filter(filter), session=session)
        return result.deleted_count > 0

    async def count(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """Count documents matching ``filter`` (default: all in collection)."""
        query = _normalize_filter(filter) if filter else {}
        return await self._db[collection].count_documents(query, session=session)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncClientSession]:
        """Start a multi-document transaction. Commits on clean exit, aborts
        on exception.

        Requires the MongoDB deployment to be a replica set (or sharded
        cluster) — a standalone ``mongod`` raises
        ``pymongo.errors.OperationFailure`` immediately.

        Usage::

            async with client.transaction() as session:
                await client.insert_one("orders", order_doc, session=session)
                await client.update_one(
                    "inventory", {"_id": sku}, {"stock": new_stock}, session=session
                )
        """
        async with (
            self._client.start_session() as session,
            await session.start_transaction(),
        ):
            yield session

    async def close(self) -> None:
        """Close the underlying MongoDB client connection."""
        await self._client.close()
