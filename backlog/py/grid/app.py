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

"""Assemble the grid FastAPI app on the generic ``forktex_core.api`` factory.

Owns the DB lifecycle: applies the ``forktex_grid`` migration and creates the
session factory on startup. ``DATABASE_URL`` selects the Postgres; if unset and
the ``pgserver`` wheel is installed, an ephemeral embedded Postgres is booted
(zero-setup POC). CORS is wide-open for the local JSX studio.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forktex_core.api import AppConfig, create_app

_GRID_SCHEMA = "forktex_grid"


def build_app(database_url: str | None = None) -> FastAPI:
    app = create_app(
        AppConfig(
            title="ForkTex Grid",
            version="0.1.0",
            description="Self-describing dynamic virtual database — the agent's persistent state space.",
        )
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from forktex.grid.routes import router

    app.include_router(router)

    # Keep the generated SDK/OpenAPI focused on /grid; the generic factory's
    # health endpoints stay live but out of the schema.
    for route in app.routes:
        if getattr(route, "path", None) in ("/health", "/health/ready"):
            route.include_in_schema = False  # type: ignore[attr-defined]

    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        from forktex_core.database import connection
        from forktex_core.grid import apply_migrations

        url = database_url or _resolve_database_url(app)
        app.state.sessionmaker = connection.init_engine(url)
        engine = connection.engine
        assert engine is not None  # set by init_engine above
        await apply_migrations(engine, schema=_GRID_SCHEMA)
        app.state.grid_schema = _GRID_SCHEMA
        try:
            yield
        finally:
            await connection.close_engine()
            server = getattr(app.state, "_embedded_pg", None)
            if server is not None:
                server.cleanup()

    # ``create_app`` builds the FastAPI without a lifespan; attach ours so the
    # DB lifecycle runs on the ASGI lifespan protocol (no deprecated on_event).
    app.router.lifespan_context = _lifespan
    return app


def _resolve_database_url(app: FastAPI) -> str:
    """Use ``DATABASE_URL`` if set, else boot an embedded Postgres (pgserver)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        import tempfile

        import pgserver
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "No DATABASE_URL set and the optional 'pgserver' wheel is not installed. "
            "Set DATABASE_URL=postgresql+asyncpg://… or `pip install pgserver`."
        ) from exc
    server = pgserver.get_server(tempfile.mkdtemp(prefix="forktex_grid_pg_"))  # type: ignore[reportPrivateImportUsage]
    app.state._embedded_pg = server
    return server.get_uri().replace("postgresql://", "postgresql+asyncpg://")


__all__ = ["build_app"]
