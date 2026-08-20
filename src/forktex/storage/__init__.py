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

"""S3-compatible object storage connector (MinIO-first).

Thin async connector — no path conventions, no content negotiation, no
image processing. Those are interface-adapter concerns in the consuming
service (per FSD rules).

Multi-bucket services use ``register`` + ``get_client``; single-bucket
services use the module-level convenience functions (``init`` / ``upload`` /
``presign`` / etc.) which operate on the ``"default"`` client.

## Single-bucket (default client)

    import forktex.storage as storage

    await storage.init(url="http://minio:9000", bucket="documents",
                       access_key="key", secret_key="secret")

    await storage.upload("invoices/abc.pdf", pdf_bytes, content_type="application/pdf")
    url = await storage.presign("invoices/abc.pdf", expires_in=3600)
    data = await storage.download("invoices/abc.pdf")
    await storage.close()

## Multi-bucket (named clients)

    from forktex.storage import register, get_client

    register("media",      url=..., bucket="news-media", ...)
    register("messaging",  url=..., bucket="messaging", ...)
    register("data-lake",  url=..., bucket="data-lake", ...)

    media_url = await get_client("media").presign("images/hero.jpg")
    await get_client("messaging").upload("conv-1/file.pdf", data)

## Secured actor callback (presigned PUT)

    # Backend generates a short-lived callback URL — the S3 signature IS the token.
    # Actor presents the URL directly to MinIO; no separate auth needed.
    put_url = await client.presign(
        "uploads/org-abc/photo.jpg",
        expires_in=900,
        method="put_object",
        content_type="image/jpeg",   # MinIO enforces this during the PUT
    )
    # Actor: PUT {put_url} with Content-Type: image/jpeg

## Browser file upload via presigned POST

    # NOTE: "multipart/form-data" here is the HTTP encoding of the browser's
    # POST body (an ordinary <form> upload) — this is unrelated to S3's own
    # chunked "Multipart Upload" API (create_multipart_upload/upload_part/
    # complete_multipart_upload), which this module does not implement.
    post_data = await client.presign_post(
        "uploads/org-abc/doc.pdf",
        content_type="application/pdf",
        max_size_bytes=10 * 1024 * 1024,
        expires_in=600,
    )
    # post_data = {"url": "...", "fields": {...}}
    # Browser POSTs multipart/form-data using post_data["url"] + post_data["fields"]

## Public-bucket direct URLs

    # When the bucket is configured as public-read, skip presigning entirely.
    client = get_client("media")
    direct_url = client.direct_url("images/hero.jpg")
    # → "http://cdn.example.com/news-media/images/hero.jpg"

Requires: pip install forktex[storage]  (aioboto3)
"""

from __future__ import annotations

from forktex.log import get_logger
from forktex.registry import ClientRegistry
from forktex.storage.client import StorageClient, StorageConfig
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
) -> StorageClient:
    """Register a named ``StorageClient`` and return it.

    Idempotent: calling ``register`` with the same name replaces the previous
    client (useful for reconfiguration without a restart). Safe to replace —
    ``StorageClient`` builds a short-lived boto3 client per call, so no
    connection pool is left behind.

    Args:
        name: Logical name used with ``get_client(name)``.
              Use ``"default"`` if you only have one bucket.
    """
    cfg = StorageConfig(
        url=url,
        bucket=bucket,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        public_url=public_url,
    )
    replaced = name in _registry.names()
    client = _registry.set(name, StorageClient(cfg))
    # Bucket + endpoint are the two things an operator needs to confirm a
    # deployment wired the right storage; the generic registry line cannot know them.
    logger.info(
        "storage: client configured",
        extra={"client": name, "bucket": bucket, "endpoint": url, "replaced": replaced},
    )
    return client


def get_client(name: str = "default") -> StorageClient:
    """Return a registered ``StorageClient`` by name.

    Raises ``ClientNotRegisteredError`` if the name has not been registered.
    """
    return _registry.get(name)


def deregister(name: str = "default") -> StorageClient | None:
    """Remove ``name`` from the registry and return the dropped client (or
    ``None`` if it wasn't registered). Idempotent.

    Symmetric with ``register``: lets tests and dev tooling restore the
    registry to a known shape without hooking into the registry directly.
    The async ``close(name)`` helper delegates here.
    """
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
    """Initialize the default storage client. Equivalent to
    ``register("default", ...)``.

    ``async`` despite awaiting nothing: registration is pure bookkeeping (the S3
    session is built lazily per call), but every other facade's ``init`` is
    awaited from a lifespan, and dropping the coroutine would break callers that
    already ``await`` this one. Symmetry with ``close`` is the point.
    """
    register(
        "default",
        url,
        bucket,
        access_key,
        secret_key,
        region=region,
        public_url=public_url,
    )


async def close(name: str = "default") -> None:
    """Deregister a named client. Idempotent. Async-shape preserved for
    callers that already ``await`` it; delegates to :func:`deregister`."""
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
    "StorageClient",
    "StorageConfig",
    "StorageError",
    "close",
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
