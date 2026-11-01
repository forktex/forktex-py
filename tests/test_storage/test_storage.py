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

import pytest
import pytest_asyncio

from forktex.storage.client import _driver_boundary
from forktex.storage import (
    ClientNotRegisteredError,
    ObjectNotFoundError,
    StorageClient,
    StorageConfig,
    StorageError,
    close,
    default,
    delete,
    download,
    exists,
    get_client,
    init,
    presign,
    presign_post,
    require_default,
    register,
    upload,
)
from forktex.storage import close as storage_close
from forktex.storage import init as storage_init


@pytest_asyncio.fixture
async def client(minio_config: dict) -> StorageClient:
    c = register(
        "test",
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
    )
    return c


@pytest_asyncio.fixture
async def public_client(minio_config: dict) -> StorageClient:
    return register(
        "test-public",
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
        public_access="bucket-policy",
    )


@pytest.mark.asyncio
async def test_upload_and_download(client: StorageClient) -> None:
    data = b"hello storage world"
    await client.upload("test/hello.txt", data, content_type="text/plain")
    result = await client.download("test/hello.txt")
    assert result == data


@pytest.mark.asyncio
async def test_exists_true_and_false(client: StorageClient) -> None:
    await client.upload("test/exists.txt", b"data")
    assert await client.exists("test/exists.txt") is True
    assert await client.exists("test/no-such-key.txt") is False


@pytest.mark.asyncio
async def test_delete(client: StorageClient) -> None:
    await client.upload("test/to-delete.txt", b"bye")
    await client.delete("test/to-delete.txt")
    assert await client.exists("test/to-delete.txt") is False


@pytest.mark.asyncio
async def test_delete_missing_key_is_a_noop(client: StorageClient) -> None:
    await client.delete("test/never-existed-xyz-abc.txt")


@pytest.mark.asyncio
async def test_upload_overwrites_existing_key(client: StorageClient) -> None:
    await client.upload("test/overwrite.txt", b"original")
    await client.upload("test/overwrite.txt", b"replaced")
    assert await client.download("test/overwrite.txt") == b"replaced"


@pytest.mark.asyncio
async def test_upload_download_key_with_special_characters(client: StorageClient) -> None:
    key = "test/special chars #1 (v2).txt"
    data = b"special key data"
    await client.upload(key, data)
    assert await client.download(key) == data
    assert await client.exists(key) is True


@pytest.mark.asyncio
async def test_download_missing_raises(client: StorageClient) -> None:
    with pytest.raises(ObjectNotFoundError):
        await client.download("test/definitely-missing-xyz-abc.txt")


@pytest.mark.asyncio
async def test_presign_get_returns_url(client: StorageClient) -> None:
    await client.upload("test/presign-target.txt", b"presigned")
    url = await client.presign("test/presign-target.txt", expires_in=300)
    assert url.startswith("http")
    assert "/test-bucket/test/presign-target.txt" in url


@pytest.mark.asyncio
async def test_presign_post_returns_policy(client: StorageClient) -> None:
    result = await client.presign_post(
        "test/multipart-target.txt",
        expires_in=300,
        content_type="text/plain",
        max_size_bytes=1024 * 1024,
    )
    assert result.url
    assert result.fields["Content-Type"] == "text/plain"
    assert "policy" in result.fields


@pytest.mark.asyncio
async def test_multi_client_registry(minio_config: dict) -> None:
    c1 = register(
        "multi-a",
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
    )
    c2 = register(
        "multi-b",
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
    )
    assert get_client("multi-a") is c1
    assert get_client("multi-b") is c2
    assert c1 is not c2


@pytest.mark.asyncio
async def test_get_unregistered_client_raises() -> None:
    with pytest.raises(ClientNotRegisteredError):
        get_client("not-registered-xyz-abc")


@pytest.mark.asyncio
async def test_direct_url(public_client: StorageClient) -> None:
    url = public_client.direct_url("images/hero.jpg")
    assert "hero.jpg" in url
    assert "test-bucket" in url


@pytest.mark.asyncio
async def test_direct_url_encodes_special_characters_in_key() -> None:
    from forktex.storage import StorageClient, StorageConfig

    c = StorageClient(
        StorageConfig(
            url="http://minio:9000",
            bucket="test-bucket",
            access_key="x",
            secret_key="y",
            public_url="http://cdn.example.com",
            public_access="bucket-policy",
        )
    )
    url = c.direct_url("images/hero #1.jpg")
    assert url == "http://cdn.example.com/test-bucket/images/hero%20%231.jpg"


def test_storage_config_masks_secrets_in_repr() -> None:
    from forktex.storage import StorageConfig

    c = StorageConfig(url="http://minio:9000", bucket="b", access_key="AKIA_SECRET", secret_key="SK_SECRET")
    assert "AKIA_SECRET" not in repr(c)
    assert "SK_SECRET" not in repr(c)
    assert "AKIA_SECRET" not in str(c)
    assert "SK_SECRET" not in str(c)
    assert c.access_key == "AKIA_SECRET"
    assert c.secret_key == "SK_SECRET"
    assert c.model_dump()["access_key"] == "AKIA_SECRET"
    assert c.model_dump()["secret_key"] == "SK_SECRET"


@pytest.mark.asyncio
async def test_ensure_bucket_creates_when_absent(minio_config: dict) -> None:
    import uuid

    from forktex.storage import StorageClient, StorageConfig

    fresh_bucket = f"ensure-bucket-test-{uuid.uuid7().hex}"
    c = StorageClient(
        StorageConfig(
            url=minio_config["url"],
            bucket=fresh_bucket,
            access_key=minio_config["access_key"],
            secret_key=minio_config["secret_key"],
        )
    )
    await c.ensure_bucket()
    await c.upload("probe.txt", b"data")
    assert await c.download("probe.txt") == b"data"


@pytest.mark.asyncio
async def test_ensure_bucket_idempotent_when_already_exists(client: StorageClient) -> None:
    await client.ensure_bucket()
    await client.ensure_bucket()


@pytest.mark.asyncio
async def test_ensure_bucket_writes_a_policy_only_when_the_bucket_declares_one(minio_config: dict) -> None:
    import uuid

    from botocore.exceptions import ClientError

    from forktex.storage import StorageClient, StorageConfig

    def _client(bucket: str, **extra: object) -> StorageClient:
        return StorageClient(
            StorageConfig(
                url=minio_config["url"],
                bucket=bucket,
                access_key=minio_config["access_key"],
                secret_key=minio_config["secret_key"],
                **extra,
            )
        )

    public = f"ensure-bucket-public-{uuid.uuid7().hex}"
    c = _client(public, public_access="bucket-policy")
    await c.ensure_bucket()
    async with c._client() as s3:
        policy = await s3.get_bucket_policy(Bucket=public)
        assert "s3:GetObject" in policy["Policy"]

    private = f"ensure-bucket-private-{uuid.uuid7().hex}"
    p = _client(private)
    await p.ensure_bucket()
    async with p._client() as s3:
        with pytest.raises(ClientError) as caught:
            await s3.get_bucket_policy(Bucket=private)
        assert caught.value.response["Error"]["Code"] in ("NoSuchBucketPolicy", "404")


@pytest.mark.asyncio
async def test_direct_url_refuses_a_bucket_with_no_public_access() -> None:
    from forktex.storage import StorageClient, StorageConfig, StorageError

    c = StorageClient(StorageConfig(url="http://minio:9000", bucket="private", access_key="x", secret_key="y"))
    with pytest.raises(StorageError, match="no public access"):
        c.direct_url("docs/invoice.pdf")


@pytest.mark.asyncio
async def test_signed_links_are_sigv4(client: StorageClient) -> None:
    import urllib.parse

    url = await client.presign("docs/invoice.pdf", expires_in=60)
    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

    assert "X-Amz-Signature" in params
    assert params["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert "AWSAccessKeyId" not in params

    post = await client.presign_post("uploads/x.bin", expires_in=60)
    assert "x-amz-signature" in post.fields
    assert "signature" not in post.fields


#


@pytest.mark.asyncio
async def test_module_facade_round_trips_through_the_default_client(minio_config: dict) -> None:
    await storage_init(
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
    )
    try:
        key = "test/facade.txt"
        assert await exists(key) is False

        await upload(key, b"via the facade", content_type="text/plain")
        assert await exists(key) is True
        assert await download(key) == b"via the facade"

        url = await presign(key)
        assert minio_config["bucket"] in url

        post = await presign_post(key)
        assert post.url and post.fields

        await delete(key)
        assert await exists(key) is False
    finally:
        await storage_close()


@pytest.mark.asyncio
async def test_module_facade_close_is_idempotent_and_deregisters(minio_config: dict) -> None:
    await storage_init(
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
    )
    get_client()

    await storage_close()
    await storage_close()

    with pytest.raises(ClientNotRegisteredError):
        get_client()


@pytest.mark.asyncio
async def test_init_fails_at_boot_when_the_bucket_is_not_reachable(minio_config: dict) -> None:
    with pytest.raises(StorageError, match="not reachable"):
        await init(
            url=minio_config["url"],
            bucket="a-bucket-that-does-not-exist",
            access_key=minio_config["access_key"],
            secret_key=minio_config["secret_key"],
        )

    with pytest.raises(ClientNotRegisteredError):
        get_client()


@pytest.mark.asyncio
async def test_init_succeeds_and_default_hands_back_the_client(minio_config: dict) -> None:
    await init(
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
    )
    try:
        assert default() is get_client()
        await default().verify()
    finally:
        await close()


@pytest.mark.asyncio
async def test_a_write_to_a_missing_bucket_raises_storage_error_not_a_driver_error(minio_config: dict) -> None:
    """upload/delete/presign let raw botocore exceptions through, so a caller
    catching StorageError around a write got an unhandled ClientError."""
    client = StorageClient(
        StorageConfig(
            url=minio_config["url"],
            bucket="a-bucket-that-does-not-exist",
            access_key=minio_config["access_key"],
            secret_key=minio_config["secret_key"],
        )
    )
    with pytest.raises(StorageError):
        await client.upload("k", b"v")
    with pytest.raises(StorageError):
        await client.delete("k")


@pytest.mark.asyncio
async def test_verify_reports_an_unreachable_endpoint_as_storage_error() -> None:
    """verify() caught only ClientError, so a wrong endpoint -- the boot-time
    failure a misconfigured deployment hits first -- escaped as raw botocore."""
    client = StorageClient(
        StorageConfig(
            url="http://127.0.0.1:1",
            bucket="any",
            access_key="k",
            secret_key="s",
        )
    )
    with pytest.raises(StorageError, match="not reachable"):
        await client.verify()


@pytest.mark.asyncio
async def test_a_presigned_get_is_actually_fetchable(minio_config: dict) -> None:
    """The SigV4 fix was only ever asserted by parsing the query string. This
    retrieves the bytes, so a signature that is well-formed but wrong fails."""
    import httpx

    client = StorageClient(StorageConfig(**minio_config))
    await client.upload("signed/hello.txt", b"hello signed world", content_type="text/plain")
    url = await client.presign("signed/hello.txt", 300)

    async with httpx.AsyncClient() as http:
        response = await http.get(url)

    assert response.status_code == 200, response.text
    assert response.content == b"hello signed world"


@pytest.mark.asyncio
async def test_a_presigned_put_actually_accepts_an_upload(minio_config: dict) -> None:
    import httpx

    client = StorageClient(StorageConfig(**minio_config))
    url = await client.presign("signed/put.txt", 300, method="put_object", content_type="text/plain")

    async with httpx.AsyncClient() as http:
        response = await http.put(url, content=b"put through a signature", headers={"Content-Type": "text/plain"})

    assert response.status_code in (200, 204), response.text
    assert await client.download("signed/put.txt") == b"put through a signature"


@pytest.mark.asyncio
async def test_default_reports_absence_instead_of_raising(minio_config: dict) -> None:
    """`default()` raised here while database's and cache's returned None, so a
    caller could not write one idiom across the facades."""
    await close()
    assert default() is None

    await init(
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
    )
    try:
        assert default() is require_default() is get_client()
    finally:
        await close()

    assert default() is None
    with pytest.raises(ClientNotRegisteredError):
        require_default()


@pytest.mark.asyncio
async def test_presign_refuses_an_argument_that_does_not_apply_to_its_method(client: StorageClient) -> None:
    """`content_type` was applied only when method was put_object and dropped in
    silence otherwise, so a caller signing a GET got a URL missing the header
    they asked for and no indication of it."""
    with pytest.raises(StorageError, match="put_object"):
        await client.presign("k", method="get_object", content_type="text/plain")

    with pytest.raises(StorageError, match="get_object"):
        await client.presign("k", method="put_object", response_content_disposition="attachment")


@pytest.mark.asyncio
async def test_a_public_read_bucket_gets_the_policy_and_serves_anonymously(minio_config: dict) -> None:
    """`ensure_bucket` builds the policy from `public_read_policy` now; this is
    the only test that proves the document S3 receives actually grants access."""
    import httpx

    bucket = "public-probe"
    client = StorageClient(
        StorageConfig(
            url=minio_config["url"],
            bucket=bucket,
            access_key=minio_config["access_key"],
            secret_key=minio_config["secret_key"],
            public_access="bucket-policy",
        )
    )
    await client.ensure_bucket()
    await client.upload("open/hello.txt", b"anyone can read this", content_type="text/plain")

    async with httpx.AsyncClient() as http:
        response = await http.get(client.direct_url("open/hello.txt"))

    assert response.status_code == 200, response.text
    assert response.content == b"anyone can read this"


@pytest.mark.asyncio
async def test_a_failed_init_leaves_a_working_default_in_place(minio_config: dict) -> None:
    """init() registered first and deregistered on a verify failure, so a second
    init() with a bad bucket evicted the client the process was already using."""
    await init(
        url=minio_config["url"],
        bucket=minio_config["bucket"],
        access_key=minio_config["access_key"],
        secret_key=minio_config["secret_key"],
    )
    working = require_default()
    try:
        with pytest.raises(StorageError):
            await init(
                url=minio_config["url"],
                bucket="a-bucket-that-does-not-exist",
                access_key=minio_config["access_key"],
                secret_key=minio_config["secret_key"],
            )
        assert default() is working
    finally:
        await close()


@pytest.mark.asyncio
async def test_a_failure_that_is_not_a_driver_error_still_reaches_the_caller_as_storage_error(
    minio_config: dict,
) -> None:
    """The boundary caught only botocore types, so a stream failure mid-download
    escaped raw to a caller that was told to catch StorageError."""
    client = StorageClient(StorageConfig(**minio_config))
    await client.upload("stream/x.bin", b"payload")

    async with _driver_boundary("probe", bucket="b"):
        pass

    with pytest.raises(StorageError, match="storage probe failed"):
        async with _driver_boundary("probe", bucket="b"):
            raise RuntimeError("the http layer gave up mid-stream")

    with pytest.raises(ObjectNotFoundError):
        async with _driver_boundary("probe", bucket="b"):
            raise ObjectNotFoundError("an AppError passes through untouched")
