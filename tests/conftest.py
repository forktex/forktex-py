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

import uuid
from typing import Any
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tests._containers import (
    ensure_minio_bucket,
    start_minio,
    start_mongo,
    start_postgres,
    start_qdrant,
    start_redis,
)


def _container_url[T](start: Callable[[], tuple[Any, T]]) -> Iterator[T]:
    container, value = start()
    yield value
    container.stop()


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[URL]:
    yield from _container_url(start_postgres)


@pytest.fixture(scope="session")
def postgres_url_str(postgres_url: URL) -> str:
    return postgres_url.render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def fresh_schema(postgres_url_str: str) -> AsyncIterator[str]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    schema = "forktex_test_" + uuid.uuid7().hex
    engine = create_async_engine(postgres_url_str)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        try:
            yield schema
        finally:
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    finally:
        await engine.dispose()


def sessions_for(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def models_sessionmaker(url: str, schema: str, *also: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from forktex.database import BaseDBModel

    translate: dict[str | None, str] = {None: schema}
    translate.update({name: schema for name in also})
    engine = create_async_engine(url, execution_options={"schema_translate_map": translate})
    try:
        async with engine.begin() as conn:
            await conn.run_sync(BaseDBModel.metadata.create_all)
        yield sessions_for(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def models_session(postgres_url_str: str, fresh_schema: str) -> AsyncIterator[AsyncSession]:
    async with models_sessionmaker(postgres_url_str, fresh_schema) as maker, maker() as session:
        yield session


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    yield from _container_url(start_redis)


@pytest_asyncio.fixture(scope="session")
async def minio_config() -> AsyncIterator[dict]:
    container, config = start_minio()
    await ensure_minio_bucket(config)
    yield config
    container.stop()


@pytest.fixture(scope="session")
def qdrant_url() -> Iterator[str]:
    yield from _container_url(start_qdrant)


@pytest.fixture(scope="session")
def mongo_url() -> Iterator[str]:
    yield from _container_url(start_mongo)
