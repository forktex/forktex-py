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
from contextlib import asynccontextmanager

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from forktex.api import AppConfig, create_app
from forktex.database import close_engine, init_engine, transactional_session


async def _database_ready() -> bool:
    async with transactional_session() as session:
        await session.execute(sa.text("SELECT 1"))
    return True


def _app(postgres_url_str: str) -> FastAPI:

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await init_engine(postgres_url_str)
        yield
        await close_engine()

    return create_app(
        AppConfig(
            title="Readiness",
            lifespan=lifespan,
            readiness_probes={"database": _database_ready},
            readiness_timeout=5.0,
        )
    )


def test_a_real_database_probe_reports_ready(postgres_url_str: str) -> None:
    with TestClient(_app(postgres_url_str)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200, response.text
        assert response.json()["checks"] == {"database": True}


def test_the_probe_reports_not_ready_once_the_engine_is_gone(postgres_url_str: str) -> None:
    import asyncio

    with TestClient(_app(postgres_url_str)) as client:
        assert client.get("/health/ready").status_code == 200
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(close_engine())

        response = client.get("/health/ready")
        assert response.status_code == 503, response.text
        body = response.json()
        assert body["checks"]["database"] is False, body
