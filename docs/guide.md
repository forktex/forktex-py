# Guide: one service, one module at a time

A small notes service, built step by step. Each step adds one module and shows
the whole `main.py`; stop at the step you need.

1. [A web app](#1-a-web-app): `api`, `log`, `error`, `types`
2. [With a database](#2-with-a-database): add `database`
3. [With a cache](#3-with-a-cache): add `cache`
4. [With file uploads](#4-with-file-uploads): add `storage`

```bash
pip install forktex uvicorn
```

## 1. A web app

No infrastructure. Notes live in memory.

```python
# main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from forktex.api import AppConfig, create_app
from forktex.error import NotFoundError
from forktex.log import get_logger, setup_logging
from forktex.types import BaseAppModel

log = get_logger(__name__)


class Note(BaseAppModel):
    note_id: str
    text: str


NOTES: dict[str, Note] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(service="notes")
    yield


app = create_app(AppConfig(title="Notes", lifespan=lifespan))


@app.put("/notes/{note_id}")
async def put_note(note_id: str, text: str) -> Note:
    NOTES[note_id] = Note(note_id=note_id, text=text)
    log.info("note saved")  # carries the request's trace_id
    return NOTES[note_id]


@app.get("/notes/{note_id}")
async def get_note(note_id: str) -> Note:
    if note_id not in NOTES:
        raise NotFoundError(f"note {note_id} not found")  # 404 with an error envelope
    return NOTES[note_id]
```

```bash
uvicorn main:app
curl -X PUT 'localhost:8000/notes/n1?text=hello'
# {"noteId":"n1","text":"hello"}
curl localhost:8000/notes/n2
# 404 {"code": "not_found", "message": "note n2 not found", "details": {}, "traceId": "01a1…"}
```

## 2. With a database

Needs PostgreSQL:

```bash
docker run -d --name forktex-db -e POSTGRES_PASSWORD=forktex -p 5432:5432 postgres:17
export DATABASE_URL=postgresql+asyncpg://postgres:forktex@localhost:5432/postgres
```

Notes move into a table. Each request gets one transaction, committed before
the response is sent.

```python
# main.py
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

import forktex.database as database
from forktex.api import AppConfig, create_app
from forktex.database import BaseDBModel, TimestampMixin, transaction
from forktex.error import NotFoundError
from forktex.log import get_logger, setup_logging
from forktex.types import BaseAppModel

log = get_logger(__name__)


class NoteRow(BaseDBModel, TimestampMixin):
    __tablename__ = "note"
    note_id: Mapped[str] = mapped_column(primary_key=True)
    text: Mapped[str]


class Note(BaseAppModel):
    note_id: str
    text: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(service="notes")
    await database.init_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    async with database.get_engine().begin() as conn:  # for this guide only: use migrations in a real service
        await conn.run_sync(BaseDBModel.metadata.create_all)
    yield
    await database.close_engine()


async def database_ready() -> bool:
    await database.verify()
    return True


app = create_app(AppConfig(title="Notes", lifespan=lifespan, readiness_probes={"database": database_ready}))
Session = Depends(transaction.dependency, scope="function")


@app.put("/notes/{note_id}")
async def put_note(note_id: str, text: str, session: AsyncSession = Session) -> Note:
    row = await session.merge(NoteRow(note_id=note_id, text=text))
    log.info("note saved")
    return Note(note_id=row.note_id, text=row.text)


@app.get("/notes/{note_id}")
async def get_note(note_id: str, session: AsyncSession = Session) -> Note:
    row = await database.get(session, NoteRow, note_id, key="note_id")
    if row is None:
        raise NotFoundError(f"note {note_id} not found")
    return Note(note_id=row.note_id, text=row.text)
```

```bash
uvicorn main:app
curl -X PUT 'localhost:8000/notes/n1?text=hello'
# {"noteId":"n1","text":"hello"}
curl localhost:8000/health/ready
# {"status":"ready","checks":{"database":true}}
```

## 3. With a cache

Also needs Redis:

```bash
docker run -d --name forktex-redis -p 6379:6379 redis:7
export REDIS_URL=redis://localhost:6379/0
```

Reads are served from Redis for a minute; a write commits, then drops the cached
copy.

```python
# main.py
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Mapped, mapped_column

import forktex.cache as cache
import forktex.database as database
from forktex.api import AppConfig, create_app
from forktex.database import BaseDBModel, TimestampMixin, transaction
from forktex.error import NotFoundError
from forktex.log import get_logger, setup_logging
from forktex.types import BaseAppModel

log = get_logger(__name__)


class NoteRow(BaseDBModel, TimestampMixin):
    __tablename__ = "note"
    note_id: Mapped[str] = mapped_column(primary_key=True)
    text: Mapped[str]


class Note(BaseAppModel):
    note_id: str
    text: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(service="notes")
    await database.init_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    await cache.init(os.environ["REDIS_URL"])
    async with database.get_engine().begin() as conn:  # for this guide only: use migrations in a real service
        await conn.run_sync(BaseDBModel.metadata.create_all)
    yield
    await cache.close()
    await database.close_engine()


async def database_ready() -> bool:
    await database.verify()
    return True


async def cache_ready() -> bool:
    await cache.verify()
    return True


app = create_app(
    AppConfig(title="Notes", lifespan=lifespan, readiness_probes={"database": database_ready, "cache": cache_ready})
)


def note_key(note_id: str) -> str:
    return cache.key_for("note", note_id)


@cache.cached(ttl=60, response_model=Note, key_builder=note_key)
async def load_note(note_id: str) -> Note:
    async with transaction() as session:
        row = await database.get(session, NoteRow, note_id, key="note_id")
    if row is None:
        raise NotFoundError(f"note {note_id} not found")
    return Note(note_id=row.note_id, text=row.text)


@app.put("/notes/{note_id}")
async def put_note(note_id: str, text: str) -> Note:
    async with transaction() as session:
        row = await session.merge(NoteRow(note_id=note_id, text=text))
    await cache.invalidate_key(note_key(note_id))  # after the commit, so no read caches the old text again
    log.info("note saved")
    return Note(note_id=row.note_id, text=row.text)


@app.get("/notes/{note_id}")
async def get_note(note_id: str) -> Note:
    return await load_note(note_id)
```

```bash
uvicorn main:app
curl -X PUT 'localhost:8000/notes/n1?text=hello'
curl localhost:8000/notes/n1   # from the database, then cached
curl localhost:8000/notes/n1   # from Redis
```

If Redis is down, reads fall back to the database: the cache never fails a
request.

## 4. With file uploads

Also needs an S3-compatible server:

```bash
docker run -d --name forktex-s3 -e MINIO_ROOT_USER=forktex -e MINIO_ROOT_PASSWORD=forktex-secret -p 9000:9000 minio/minio server /data
export S3_URL=http://localhost:9000 S3_BUCKET=notes S3_ACCESS_KEY=forktex S3_SECRET_KEY=forktex-secret
```

Step 3's `main.py`, plus storage in the lifespan, a readiness probe, and two
routes: one stores an attachment, the other hands out a link to it.

```python
# main.py
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy.orm import Mapped, mapped_column

import forktex.cache as cache
import forktex.database as database
import forktex.storage as storage
from forktex.api import AppConfig, create_app
from forktex.database import BaseDBModel, TimestampMixin, transaction
from forktex.error import NotFoundError
from forktex.log import get_logger, setup_logging
from forktex.types import BaseAppModel

log = get_logger(__name__)


class NoteRow(BaseDBModel, TimestampMixin):
    __tablename__ = "note"
    note_id: Mapped[str] = mapped_column(primary_key=True)
    text: Mapped[str]


class Note(BaseAppModel):
    note_id: str
    text: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(service="notes")
    await database.init_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    await cache.init(os.environ["REDIS_URL"])
    await storage.init(
        os.environ["S3_URL"], os.environ["S3_BUCKET"], os.environ["S3_ACCESS_KEY"], os.environ["S3_SECRET_KEY"]
    )
    async with database.get_engine().begin() as conn:  # for this guide only: use migrations in a real service
        await conn.run_sync(BaseDBModel.metadata.create_all)
    await storage.get_client().ensure_bucket()
    yield
    await cache.close()
    await database.close_engine()


async def database_ready() -> bool:
    await database.verify()
    return True


async def cache_ready() -> bool:
    await cache.verify()
    return True


async def storage_ready() -> bool:
    await storage.verify()
    return True


app = create_app(
    AppConfig(
        title="Notes",
        lifespan=lifespan,
        readiness_probes={"database": database_ready, "cache": cache_ready, "storage": storage_ready},
    )
)


def note_key(note_id: str) -> str:
    return cache.key_for("note", note_id)


@cache.cached(ttl=60, response_model=Note, key_builder=note_key)
async def load_note(note_id: str) -> Note:
    async with transaction() as session:
        row = await database.get(session, NoteRow, note_id, key="note_id")
    if row is None:
        raise NotFoundError(f"note {note_id} not found")
    return Note(note_id=row.note_id, text=row.text)


@app.put("/notes/{note_id}")
async def put_note(note_id: str, text: str) -> Note:
    async with transaction() as session:
        row = await session.merge(NoteRow(note_id=note_id, text=text))
    await cache.invalidate_key(note_key(note_id))  # after the commit, so no read caches the old text again
    log.info("note saved")
    return Note(note_id=row.note_id, text=row.text)


@app.get("/notes/{note_id}")
async def get_note(note_id: str) -> Note:
    return await load_note(note_id)


@app.put("/notes/{note_id}/attachment")
async def put_attachment(note_id: str, request: Request) -> dict[str, str]:
    await load_note(note_id)  # 404 for an unknown note
    await storage.upload(f"attachments/{note_id}", await request.body(), content_type="application/octet-stream")
    return {"stored": note_id}


@app.get("/notes/{note_id}/attachment")
async def attachment_link(note_id: str) -> dict[str, str]:
    key = f"attachments/{note_id}"
    if not await storage.exists(key):
        raise NotFoundError(f"note {note_id} has no attachment")
    return {"url": await storage.presign(key, expires_in=600)}  # valid for 10 minutes, no other credential
```

```bash
uvicorn main:app
curl -X PUT 'localhost:8000/notes/n1?text=hello'
curl -X PUT localhost:8000/notes/n1/attachment --data-binary @report.pdf
curl localhost:8000/notes/n1/attachment
# {"url":"http://localhost:9000/notes/attachments/n1?X-Amz-Algorithm=AWS4-HMAC-SHA256&…"}
curl localhost:8000/health/ready
# {"status":"ready","checks":{"database":true,"cache":true,"storage":true}}
```

## Going further

- [database](database.md): migrations instead of `create_all`, pagination,
  client-supplied filters, advisory locks.
- [cache](cache.md): stale-while-revalidate, prefix invalidation.
- [storage](storage.md): upload URLs for browsers, several buckets.
- [api](api.md): CORS, configuration, the status table.
- [log](log.md): trace ids in background jobs and threads.
