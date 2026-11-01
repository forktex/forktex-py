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

from forktex.log import get_logger
from forktex.registry import ClientRegistry
from forktex.storage.client import PublicAccess, StorageClient, StorageConfig
from forktex.storage.errors import ClientNotRegisteredError, ObjectNotFoundError, StorageError

logger = get_logger(__name__)


_registry: ClientRegistry[StorageClient] = ClientRegistry("storage", ClientNotRegisteredError)


def register(
    name: str,
    url: str,
    bucket: str,
    access_key: str,
    secret_key: str,
    *,
    region: str = "us-east-1",
    public_url: str | None = None,
    public_access: PublicAccess = "none",
) -> StorageClient:
    cfg = StorageConfig(
        url=url,
        bucket=bucket,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        public_url=public_url,
        public_access=public_access,
    )
    replaced = name in _registry.names()
    client = _registry.set(name, StorageClient(cfg))
    logger.info(
        "storage: client configured",
        extra={"client": name, "bucket": bucket, "endpoint": url, "replaced": replaced},
    )
    return client


def default() -> StorageClient:
    return get_client()


def get_client(name: str = "default") -> StorageClient:
    return _registry.get(name)


def deregister(name: str = "default") -> StorageClient | None:
    return _registry.pop(name)


async def init(
    url: str,
    bucket: str,
    access_key: str,
    secret_key: str,
    *,
    region: str = "us-east-1",
    public_url: str | None = None,
) -> None:
    register(
        "default",
        url,
        bucket,
        access_key,
        secret_key,
        region=region,
        public_url=public_url,
    )
    await get_client().verify()


async def close(name: str = "default") -> None:
    deregister(name)


async def upload(key: str, data: bytes, *, content_type: str = "application/octet-stream") -> None:
    await get_client().upload(key, data, content_type=content_type)


async def download(key: str) -> bytes:
    return await get_client().download(key)


async def delete(key: str) -> None:
    await get_client().delete(key)


async def exists(key: str) -> bool:
    return await get_client().exists(key)


async def presign(
    key: str,
    expires_in: int = 3600,
    *,
    method: str = "get_object",
    content_type: str | None = None,
    response_content_disposition: str | None = None,
) -> str:
    return await get_client().presign(
        key,
        expires_in,
        method=method,
        content_type=content_type,
        response_content_disposition=response_content_disposition,
    )


async def presign_post(
    key: str,
    *,
    expires_in: int = 3600,
    content_type: str | None = None,
    max_size_bytes: int | None = None,
) -> dict:
    return await get_client().presign_post(
        key,
        expires_in=expires_in,
        content_type=content_type,
        max_size_bytes=max_size_bytes,
    )


__all__ = [
    "ClientNotRegisteredError",
    "ObjectNotFoundError",
    "PublicAccess",
    "StorageClient",
    "StorageConfig",
    "StorageError",
    "close",
    "default",
    "delete",
    "deregister",
    "download",
    "exists",
    "get_client",
    "init",
    "presign",
    "presign_post",
    "register",
    "upload",
]
