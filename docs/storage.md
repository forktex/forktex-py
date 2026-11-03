# forktex.storage

Thin async S3/MinIO connector for opaque binary objects: upload, download, delete, existence
checks, presigned GET/PUT URLs and presigned browser POST policies. No path conventions, no
content negotiation, no image processing — those belong in the consuming service.

## Wiring

```bash
export S3_URL=http://localhost:9000 S3_BUCKET=media S3_ACCESS_KEY=forktex S3_SECRET_KEY=forktex-secret
```

```python
# media.py
import asyncio
import os

import forktex.storage as storage


async def main() -> None:
    media = storage.register(  # performs no I/O
        "media",
        url=os.environ["S3_URL"],
        bucket=os.environ["S3_BUCKET"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
        public_url=os.environ.get("S3_PUBLIC_URL"),  # the address browsers reach, when it differs
    )
    await media.ensure_bucket()  # creates it if missing
    await media.verify()  # fails fast on a wrong endpoint, credential or bucket

    await media.upload("reports/today.txt", b"all good", content_type="text/plain")
    print(await media.download("reports/today.txt"), await media.exists("reports/nope.txt"))

    # A browser downloads with this URL, for 10 minutes, with no other credential.
    print(await media.presign("reports/today.txt", expires_in=600))

    # An untrusted client uploads with this one; the content type is enforced during the PUT.
    print(await media.presign("uploads/photo.jpg", expires_in=900, method="put_object", content_type="image/jpeg"))

    # A browser <form> posts the file with these fields, limited to 10 MB of PDF.
    form = await media.presign_post(
        "uploads/doc.pdf", expires_in=600, content_type="application/pdf", max_size_bytes=10 * 1024 * 1024
    )
    print(form.url, sorted(form.fields))

    storage.deregister("media")


asyncio.run(main())
```

`storage.init(url, bucket, access_key, secret_key)` registers the client named
`"default"`, which the module-level `upload`, `download`, `delete`, `exists`,
`presign` and `presign_post` use. Any other name is reached with
`get_client(name)`.

The registry is **per-process**: a worker registers its own clients at startup.
Forgetting shows up as `ClientNotRegisteredError` on first use, not at boot.
Registering a name again replaces its client.

## Public surface

| Name | Description |
|---|---|
| `register(name, url, bucket, access_key, secret_key, *, region="us-east-1", public_url=None, public_access="none")` | Build and store a named client; returns it. |
| `default()` | The `"default"` client — what the module-level operations use. |
| `require_default()` | The same, raising `ClientNotRegisteredError` instead of returning `None`. |
| `verify()` / `StorageClient.verify()` | Async. `head_bucket`; creates nothing. Raises `StorageUnreachableError`. |
| `get_client(name="default")` | Look up a registered client. |
| `deregister(name="default")` | Drop a name; returns the dropped client or `None`. Idempotent. |
| `init(url, bucket, access_key, secret_key, *, region="us-east-1", public_url=None)` | Async. `register("default", ...)`. For `public_access`, use `register`. |
| `close(name="default")` | Async. Delegates to `deregister`; nothing is actually closed. |
| `upload(key, data, *, content_type=...)` | Async. `put_object` on the default client. Overwrites. |
| `download(key)` | Async. Returns `bytes`. |
| `delete(key)` | Async. `delete_object`; a missing key is a no-op. |
| `exists(key)` | Async. `head_object` → `bool`. |
| `presign(key, expires_in=3600, *, method: PresignMethod = "get_object", content_type=None, response_content_disposition=None)` | Async. Presigned URL. `content_type` signs a `put_object` and `response_content_disposition` a `get_object`; the other pairing raises. |
| `presign_post(key, *, expires_in=3600, content_type=None, max_size_bytes=None)` | Async. A `PresignedPost` for a browser form upload. |
| `StorageClient` | Per-bucket client. The same six operations plus `ensure_bucket()`, `verify()` and `direct_url(key)`. |
| `StorageConfig` | Frozen Pydantic value object: `url`, `bucket`, `access_key`, `secret_key`, `region`, `public_url`, `public_access`. |
| `StorageError` | Base error, `AppErrorCode.INTERNAL`. |
| `ObjectNotFoundError` | `AppErrorCode.NOT_FOUND`. |
| `ClientNotRegisteredError` | `AppErrorCode.INTERNAL`. |
| `PublicAccess` | `Literal["none", "bucket-policy", "credentialed-proxy"]` — the type of `register(..., public_access=...)`. |

### Bucket policy

`public_access="bucket-policy"` makes `ensure_bucket` send this document, and these are the types
it is built from — construct one yourself to grant something narrower.

| Name | What it is |
|:---|:---|
| `BucketPolicy` | The document. `to_json()` is what `PutBucketPolicy` takes. Frozen. |
| `BucketPolicyStatement` | One statement: `action`, `resource`, `effect`, `principal`. |
| `BucketPolicyPrincipal` | Who it applies to; defaults to everyone (`{"AWS": ["*"]}`). |
| `public_read_policy(bucket)` | Anonymous `s3:GetObject` on every object — what `ensure_bucket` applies. |
| `object_arn(bucket, key_pattern="*")` | `arn:aws:s3:::<bucket>/<pattern>`. |
| `PostPolicy` | The conditions and form fields behind `presign_post`. |
| `PresignedPost` | `url` + `fields`, returned by `presign_post`. |
| `PresignParams` | The `Params` behind `presign`; unset values are omitted. |
| `PresignMethod` | `"get_object" | "put_object"`. |

Fields are snake_case in Python and serialise to AWS's own casing.

## Errors

| Raised | When | Catch? |
|---|---|---|
| `ClientNotRegisteredError` | `get_client(name)` or `require_default()` for an unregistered name. Message lists the registered names. | No — a wiring bug. |
| `ObjectNotFoundError(key)` | `download()` on a missing key. | Yes, when a missing object is expected. |
| `StorageUnreachableError` | `verify()` — wrong endpoint, credential or bucket. | At startup only, if you call `verify()`. |
| `StorageError("storage <operation> failed")` | any other failure in `upload`, `download`, `delete`, `exists`, `presign`, `presign_post` or `ensure_bucket`. | Yes, at a request boundary. |
| `StorageError` | `direct_url()` on a bucket with `public_access="none"`; `presign()` given `content_type` for a `get_object` or `response_content_disposition` for a `put_object`. | No — a wiring bug. |

Nothing the S3 driver raises escapes as a botocore type. The message names only the operation;
the detail is logged with the AWS error code and reaches the caller as `__cause__`.

## Gotchas

- **`close()` only deregisters.** Boto clients are created and closed per call, so there is no
  long-lived connection to release.
- **`exists()` returns `False` for a missing key** — it does not raise `ObjectNotFoundError`. Only
  `download()` does.
- **`upload()` overwrites silently.** There is no conditional-put or if-none-match option.
- **No listing API.** There is no `list_objects` and no pagination; keep your own index.
- **`public_url` matters for presigning.** Presigned URLs and `direct_url()` are generated against
  `public_url or url`; ordinary uploads/downloads always use `url`. If the internal Docker endpoint
  differs from the browser-reachable one and you leave `public_url` unset, the URLs you hand out
  will not resolve from outside the network.
- **`content_type` only applies to `method="put_object"`**, and `response_content_disposition` only
  to `method="get_object"`; the other combination raises `StorageError`.
- **`direct_url()` raises unless the bucket declares `public_access`.** It performs no auth check
  otherwise. The key is URL-encoded with `urllib.parse.quote`.
- **`public_access="bucket-policy"` makes the bucket world-readable.** `ensure_bucket()` applies the
  policy and logs at `warning` level when it does. It is the only call in the module that is not
  plain S3 — Garage answers `PutBucketPolicy` with 501 — so a bucket that does not need anonymous
  readers should leave `public_access` at `"none"`.
- **Presigned URLs are SigV4, path-style.** SigV2 links are honoured by MinIO and rejected by
  Garage, R2 and current AWS regions.
- **`ensure_bucket()` only creates on a genuine 404/`NoSuchBucket`.** A 403 from `head_bucket`
  propagates rather than being reinterpreted as "create it".
- **Credentials are `repr`-suppressed.** `StorageConfig.access_key`/`secret_key` use
  `Field(repr=False)` so they do not leak into logs or tracebacks — but `StorageConfig` is a frozen
  Pydantic value object, not a dataclass, so do not construct it positionally.
