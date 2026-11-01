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

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Literal, cast
from urllib.parse import quote

import aioboto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import Field

from forktex.error import AppError
from forktex.log import get_logger
from forktex.storage.errors import ObjectNotFoundError, StorageError, StorageUnreachableError
from forktex.storage.policy import (
    PostPolicy,
    PresignedPost,
    PresignMethod,
    PresignParams,
    public_read_policy,
)
from forktex.types import BaseValueObject

logger = get_logger(__name__)

PublicAccess = Literal["none", "bucket-policy", "credentialed-proxy"]

_MISSING_OBJECT = frozenset({"404", "NoSuchKey"})
_MISSING_BUCKET = frozenset({"404", "NoSuchBucket"})
_SIGNING = Config(signature_version="s3v4", s3={"addressing_style": "path"})


class StorageConfig(BaseValueObject):
    url: str
    """Internal S3 endpoint (used for uploads/downloads/deletes)."""
    bucket: str
    access_key: str = Field(repr=False)
    """Excluded from repr()/str() so it never leaks into logs/tracebacks."""
    secret_key: str = Field(repr=False)
    """Excluded from repr()/str() so it never leaks into logs/tracebacks."""
    region: str = "us-east-1"
    public_url: str | None = None
    """Public-facing endpoint for presigned URL generation. Defaults to ``url``.
    Set when the internal Docker endpoint differs from the browser-reachable URL
    (e.g. internal=``http://minio:9000``, public=``http://localhost:9100``)."""
    public_access: PublicAccess = "none"
    """How an unauthenticated reader reaches this bucket's objects.

    - ``"none"`` — credentials required; ``direct_url`` refuses and ``presign``
      is the way in.
    - ``"bucket-policy"`` — ``ensure_bucket`` grants anonymous ``GetObject``
      with an S3 bucket policy. The only non-portable option: ``PutBucketPolicy``
      is a MinIO-family and SeaweedFS feature, and Garage answers it 501.
    - ``"credentialed-proxy"`` — something in front signs the upstream request
      or streams the object itself. A proxy that forwards the request unsigned
      does not qualify; the bucket would still have to be anonymously readable.
    """


class StorageClient:
    def __init__(self, config: StorageConfig) -> None:
        self._config = config
        self._session = aioboto3.Session(
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region,
        )

    def _endpoint(self, *, public: bool) -> str:
        return (self._config.public_url or self._config.url) if public else self._config.url

    def _client(self, *, public: bool = False) -> AbstractAsyncContextManager[Any]:
        endpoint = self._endpoint(public=public)
        return cast(
            AbstractAsyncContextManager[Any],
            self._session.client("s3", endpoint_url=endpoint, config=_SIGNING),
        )

    def direct_url(self, key: str) -> str:
        if self._config.public_access == "none":
            raise StorageError(
                f"bucket {self._config.bucket!r} has no public access configured; "
                "use presign() or set public_access on its StorageConfig"
            )
        base = self._endpoint(public=True).rstrip("/")
        return f"{base}/{self._config.bucket}/{quote(key)}"

    async def ensure_bucket(self) -> None:
        async with _driver_boundary("bucket setup", bucket=self._config.bucket), self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self._config.bucket)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code not in _MISSING_BUCKET:
                    logger.error(
                        "storage: bucket check failed",
                        extra={"bucket": self._config.bucket, "aws_code": code},
                    )
                    raise
                logger.info("storage: creating bucket", extra={"bucket": self._config.bucket})
                await s3.create_bucket(Bucket=self._config.bucket)

            if self._config.public_access == "bucket-policy":
                logger.warning(
                    "storage: applying public-read bucket policy",
                    extra={"bucket": self._config.bucket},
                )
                await s3.put_bucket_policy(
                    Bucket=self._config.bucket,
                    Policy=public_read_policy(self._config.bucket).to_json(),
                )

    async def verify(self) -> None:
        try:
            async with self._client() as s3:
                await s3.head_bucket(Bucket=self._config.bucket)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnreachableError("storage bucket is not reachable") from exc

    async def upload(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        logger.debug(
            "storage: uploading object",
            extra={"bucket": self._config.bucket, "key": key, "bytes": len(data), "content_type": content_type},
        )
        async with _driver_boundary("upload", bucket=self._config.bucket, key=key), self._client() as s3:
            await s3.put_object(
                Bucket=self._config.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

    async def download(self, key: str) -> bytes:
        async with _driver_boundary("download", bucket=self._config.bucket, key=key), self._client() as s3:
            try:
                response = await s3.get_object(Bucket=self._config.bucket, Key=key)
            except ClientError as exc:
                if exc.response["Error"]["Code"] not in _MISSING_OBJECT:
                    raise
                logger.info("storage: object not found", extra={"bucket": self._config.bucket, "key": key})
                raise ObjectNotFoundError(key) from exc
            async with response["Body"] as stream:
                return await stream.read()

    async def delete(self, key: str) -> None:
        logger.info("storage: deleting object", extra={"bucket": self._config.bucket, "key": key})
        async with _driver_boundary("delete", bucket=self._config.bucket, key=key), self._client() as s3:
            await s3.delete_object(Bucket=self._config.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        async with (
            _driver_boundary("existence check", bucket=self._config.bucket, key=key),
            self._client() as s3,
        ):
            try:
                await s3.head_object(Bucket=self._config.bucket, Key=key)
            except ClientError as exc:
                if exc.response["Error"]["Code"] in _MISSING_OBJECT:
                    return False
                raise
            return True

    async def presign(
        self,
        key: str,
        expires_in: int = 3600,
        *,
        method: PresignMethod = "get_object",
        content_type: str | None = None,
        response_content_disposition: str | None = None,
    ) -> str:
        if content_type is not None and method != "put_object":
            raise StorageError(f"content_type signs a put_object, not a {method}")
        if response_content_disposition is not None and method != "get_object":
            raise StorageError(f"response_content_disposition signs a get_object, not a {method}")

        params = PresignParams(
            bucket=self._config.bucket,
            key=key,
            content_type=content_type,
            response_content_disposition=response_content_disposition,
        )
        async with _driver_boundary("presign", bucket=self._config.bucket, key=key), self._client(public=True) as s3:
            return await s3.generate_presigned_url(
                method,
                Params=params.to_params(),
                ExpiresIn=expires_in,
            )

    async def presign_post(
        self,
        key: str,
        *,
        expires_in: int = 3600,
        content_type: str | None = None,
        max_size_bytes: int | None = None,
    ) -> PresignedPost:
        policy = PostPolicy(content_type=content_type, max_size_bytes=max_size_bytes)
        async with (
            _driver_boundary("presigned post", bucket=self._config.bucket, key=key),
            self._client(public=True) as s3,
        ):
            signed = await s3.generate_presigned_post(
                Bucket=self._config.bucket,
                Key=key,
                Fields=policy.fields() or None,
                Conditions=policy.conditions() or None,
                ExpiresIn=expires_in,
            )
            return PresignedPost.model_validate(signed)


@asynccontextmanager
async def _driver_boundary(operation: str, **context: object) -> AsyncIterator[None]:
    try:
        yield
    except AppError:
        raise
    except Exception as exc:
        logger.error("storage: operation failed", extra={"operation": operation, **context})
        raise StorageError(f"storage {operation} failed") from exc


__all__ = [
    "StorageClient",
    "StorageConfig",
]
