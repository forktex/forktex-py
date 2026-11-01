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
    if name in _registry.names():
        logger.warning(
            "store.register(%r) is replacing a live client; its connection pool cannot "
            "be closed from a sync call and will leak. Use `await store.close(%r)` first.",
            name,
            name,
        )
    return _registry.set(name, StoreClient(StoreConfig(url=url, database=database)))


def default() -> StoreClient:
    return get_client()


def get_client(name: str = "default") -> StoreClient:
    return _registry.get(name)


def deregister(name: str = "default") -> StoreClient | None:
    return _registry.pop(name)


async def init(url: str, database: str) -> None:
    register("default", url, database)


async def close(name: str = "default") -> None:
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
    return get_client().transaction()


__all__ = [
    "ClientNotRegisteredError",
    "StoreClient",
    "StoreConfig",
    "StoreError",
    "close",
    "count",
    "default",
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
