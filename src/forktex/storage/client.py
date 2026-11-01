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
from typing import TYPE_CHECKING, Any, Literal, cast
from urllib.parse import quote

from pydantic import Field

from forktex.log import get_logger
from forktex.storage.errors import ObjectNotFoundError, StorageError
from forktex.types import BaseValueObject

if TYPE_CHECKING:
    from types import ModuleType

    from botocore.config import Config

logger = get_logger(__name__)

PublicAccess = Literal["none", "bucket-policy", "credentialed-proxy"]


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
        self._aioboto3 = _get_aioboto3()
        self._session = self._aioboto3.Session(
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region,
        )

    def _client(self, *, public: bool = False) -> AbstractAsyncContextManager[Any]:
        public_endpoint = self._config.public_url or self._config.url
        endpoint = public_endpoint if public else self._config.url
        return cast(
            AbstractAsyncContextManager[Any],
            self._session.client("s3", endpoint_url=endpoint, config=_signing_config()),
        )

    def direct_url(self, key: str) -> str:
        if self._config.public_access == "none":
            raise StorageError(
                f"bucket {self._config.bucket!r} has no public access configured; "
                "use presign() or set public_access on its StorageConfig"
            )
        base = (self._config.public_url or self._config.url).rstrip("/")
        return f"{base}/{self._config.bucket}/{quote(key)}"

    async def ensure_bucket(self) -> None:
        import json

        from botocore.exceptions import ClientError

        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self._config.bucket)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code not in ("404", "NoSuchBucket"):
                    logger.error(
                        "storage: bucket check failed",
                        extra={"bucket": self._config.bucket, "aws_code": code},
                    )
                    raise
                logger.info("storage: creating bucket", extra={"bucket": self._config.bucket})
                await s3.create_bucket(Bucket=self._config.bucket)

            if self._config.public_access == "bucket-policy":
                policy = json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"AWS": ["*"]},
                                "Action": ["s3:GetObject"],
                                "Resource": [f"arn:aws:s3:::{self._config.bucket}/*"],
                            }
                        ],
                    }
                )
                logger.warning(
                    "storage: applying public-read bucket policy",
                    extra={"bucket": self._config.bucket},
                )
                await s3.put_bucket_policy(Bucket=self._config.bucket, Policy=policy)

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
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._config.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

    async def download(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._config.bucket, Key=key)
                async with response["Body"] as stream:
                    return await stream.read()
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("NoSuchKey", "404"):
                logger.info("storage: object not found", extra={"bucket": self._config.bucket, "key": key})
                raise ObjectNotFoundError(key) from exc
            logger.error(
                "storage: download failed",
                extra={"bucket": self._config.bucket, "key": key, "aws_code": code},
            )
            raise StorageError("storage download failed") from exc
        except Exception as exc:
            logger.exception("storage: download failed", extra={"bucket": self._config.bucket, "key": key})
            raise StorageError("storage download failed") from exc

    async def delete(self, key: str) -> None:
        logger.info("storage: deleting object", extra={"bucket": self._config.bucket, "key": key})
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._config.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            async with self._client() as s3:
                await s3.head_object(Bucket=self._config.bucket, Key=key)
                return True
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("404", "NoSuchKey"):
                return False
            logger.error(
                "storage: existence check failed",
                extra={"bucket": self._config.bucket, "key": key, "aws_code": code},
            )
            raise StorageError("storage existence check failed") from exc
        except Exception as exc:
            logger.exception("storage: existence check failed", extra={"bucket": self._config.bucket, "key": key})
            raise StorageError("storage existence check failed") from exc

    async def presign(
        self,
        key: str,
        expires_in: int = 3600,
        *,
        method: str = "get_object",
        content_type: str | None = None,
        response_content_disposition: str | None = None,
    ) -> str:
        params: dict[str, Any] = {"Bucket": self._config.bucket, "Key": key}
        if content_type and method == "put_object":
            params["ContentType"] = content_type
        if response_content_disposition and method == "get_object":
            params["ResponseContentDisposition"] = response_content_disposition

        async with self._client(public=True) as s3:
            return await s3.generate_presigned_url(
                method,
                Params=params,
                ExpiresIn=expires_in,
            )

    async def presign_post(
        self,
        key: str,
        *,
        expires_in: int = 3600,
        content_type: str | None = None,
        max_size_bytes: int | None = None,
    ) -> dict[str, Any]:
        conditions: list[Any] = []
        fields: dict[str, str] = {}

        if content_type:
            conditions.append({"Content-Type": content_type})
            fields["Content-Type"] = content_type

        if max_size_bytes is not None:
            conditions.append(["content-length-range", 1, max_size_bytes])

        async with self._client(public=True) as s3:
            return await s3.generate_presigned_post(
                Bucket=self._config.bucket,
                Key=key,
                Fields=fields or None,
                Conditions=conditions or None,
                ExpiresIn=expires_in,
            )


def _signing_config() -> Config:
    from botocore.config import Config

    return Config(signature_version="s3v4", s3={"addressing_style": "path"})


def _get_aioboto3() -> ModuleType:
    try:
        import aioboto3

        return aioboto3
    except ImportError as exc:
        raise ImportError("Install 'forktex[storage]' (aioboto3) to use forktex.storage") from exc


__all__ = [
    "StorageClient",
    "StorageConfig",
]
