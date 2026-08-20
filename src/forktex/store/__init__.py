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

"""Schemaless document store connector (MongoDB-first).

Thin async connector — no schema validation, no aggregation pipeline
builder. Distinct from ``forktex.storage``, which holds opaque binary
blobs; this holds structured BSON/JSON documents with query support.

Multi-database services use ``register`` + ``get_client``; single-database
services use the module-level convenience functions (``init`` / ``insert_one``
/ ``find`` / etc.) which operate on the ``"default"`` client.

## Single-database (default client)

    import forktex.store as store

    await store.init(url="mongodb://localhost:27017", database="app")

    doc_id = await store.insert_one("events", {"kind": "signup", "user_id": "u-1"})
    event = await store.find_one("events", {"_id": doc_id})
    events = await store.find("events", {"kind": "signup"}, limit=50)
    await store.close()

## Multi-database (named clients)

    from forktex.store import register, get_client

    register("analytics", url=..., database="analytics")
    register("audit",     url=..., database="audit")

    await get_client("audit").insert_one("log", {"actor": "u-1", "action": "delete"})

## Multi-document transactions

Requires the MongoDB deployment to be a replica set (or sharded cluster) —
a standalone ``mongod`` raises ``pymongo.errors.OperationFailure`` on
``start_transaction()``.

    async with store.transaction() as session:
        await store.insert_one("orders", order_doc, session=session)
        await store.update_one(
            "inventory", {"_id": sku}, {"stock": new_stock}, session=session
        )
    # commits automatically on clean exit; aborts on exception

Requires: pip install forktex[store]  (pymongo)
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any

from forktex.log import get_logger
from forktex.registry import ClientRegistry
from forktex.store.client import StoreClient, StoreConfig
from forktex.store.errors import ClientNotRegisteredError, StoreError

if TYPE_CHECKING:
    from pymongo.asynchronous.client_session import AsyncClientSession

logger = get_logger(__name__)


_registry: ClientRegistry[StoreClient] = ClientRegistry("store", ClientNotRegisteredError)


def register(name: str, url: str, database: str) -> StoreClient:
    """Register a named ``StoreClient`` and return it.

    To **reconfigure** an existing name, ``await close(name)`` first. Replacing a
    live registration here cannot close the client it displaces — ``register`` is
    sync and ``StoreClient.close`` is a coroutine — so the displaced
    ``AsyncMongoClient`` keeps its connection pool open until the process exits.
    Doing so logs a warning rather than failing, because a leaked pool is not
    worth crashing a startup path over; the log is how you find it.

    Args:
        name: Logical name used with ``get_client(name)``.
              Use ``"default"`` if you only have one database.
    """
    if name in _registry.names():
        logger.warning(
            "store.register(%r) is replacing a live client; its connection pool cannot "
            "be closed from a sync call and will leak. Use `await store.close(%r)` first.",
            name,
            name,
        )
    return _registry.set(name, StoreClient(StoreConfig(url=url, database=database)))


def get_client(name: str = "default") -> StoreClient:
    """Return a registered ``StoreClient`` by name.

    Raises ``ClientNotRegisteredError`` if the name has not been registered.
    """
    return _registry.get(name)


def deregister(name: str = "default") -> StoreClient | None:
    """Remove ``name`` from the registry and return the dropped client (or
    ``None`` if it wasn't registered). Idempotent."""
    return _registry.pop(name)


async def init(url: str, database: str) -> None:
    """Initialize the default store client. Equivalent to
    ``register("default", ...)``.

    ``async`` despite awaiting nothing: the Mongo client connects lazily, so
    registration is pure bookkeeping. The coroutine shape is kept so callers can
    ``await store.init(...)`` from a lifespan exactly as they do for the other
    facades — and so removing it later is not a breaking change for them.
    """
    register("default", url, database)


async def close(name: str = "default") -> None:
    """Close and deregister a named client. Idempotent."""
    client = deregister(name)
    if client is not None:
        await client.close()


async def insert_one(
    collection: str,
    document: dict[str, Any],
    *,
    id: str | None = None,
    session: AsyncClientSession | None = None,
) -> str:
    return await get_client().insert_one(collection, document, id=id, session=session)


async def find_one(
    collection: str,
    filter: dict[str, Any],
    *,
    session: AsyncClientSession | None = None,
) -> dict[str, Any] | None:
    return await get_client().find_one(collection, filter, session=session)


async def find(
    collection: str,
    filter: dict[str, Any] | None = None,
    *,
    limit: int = 100,
    session: AsyncClientSession | None = None,
) -> list[dict[str, Any]]:
    return await get_client().find(collection, filter, limit=limit, session=session)


async def update_one(
    collection: str,
    filter: dict[str, Any],
    update: dict[str, Any],
    *,
    upsert: bool = False,
    session: AsyncClientSession | None = None,
) -> bool:
    return await get_client().update_one(collection, filter, update, upsert=upsert, session=session)


async def delete_one(
    collection: str,
    filter: dict[str, Any],
    *,
    session: AsyncClientSession | None = None,
) -> bool:
    return await get_client().delete_one(collection, filter, session=session)


async def count(
    collection: str,
    filter: dict[str, Any] | None = None,
    *,
    session: AsyncClientSession | None = None,
) -> int:
    return await get_client().count(collection, filter, session=session)


def transaction() -> AbstractAsyncContextManager[AsyncClientSession]:
    """Start a multi-document transaction on the default client. See
    ``StoreClient.transaction`` for usage and requirements."""
    return get_client().transaction()


__all__ = [
    "ClientNotRegisteredError",
    "StoreClient",
    "StoreConfig",
    "StoreError",
    "close",
    "count",
    "delete_one",
    "deregister",
    "find",
    "find_one",
    "get_client",
    "init",
    "insert_one",
    "register",
    "transaction",
    "update_one",
]
