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

"""Grid-backed persistence adaptor — forktex-py's main state backend.

``GridStore`` is the thin, in-process layer that makes ``forktex_core[grid]``
forktex-py's source of truth: it provisions per-namespace system tables on first
use (idempotent) and reads/writes records through grid's validated write path +
query engine. Domain helpers (``register_project`` / ``record_agent_run`` / …)
target the right namespace from :mod:`forktex.grid.domains`.

Backing store: ``DATABASE_URL`` env → manifest-derived (Dockerized PG) →
embedded ``pgserver`` (zero-config). The CLI can still run statelessly; callers
that don't open a store simply don't touch the DB. Large artifacts stay on disk;
only references/fingerprints are stored here.
"""

from __future__ import annotations

import tempfile
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from forktex_core.common.errors import NotFoundError
from forktex_core.grid import (
    apply_migrations,
    create_column,
    create_row,
    create_table,
    get_table,
    query_rows,
)

from forktex.grid import domains, runtime

_SCHEMA = "forktex_grid"

# Domain table definitions (provisioned on first use).
PROJECT_COLUMNS = [
    {
        "key": "fingerprint",
        "label": "Fingerprint",
        "type_id": "text",
        "is_required": True,
        "is_unique": True,
    },
    {"key": "name", "label": "Name", "type_id": "text"},
    {"key": "root", "label": "Root path", "type_id": "text"},
]
AGENT_RUN_COLUMNS = [
    {"key": "agent_id", "label": "Agent id", "type_id": "text", "is_required": True},
    {"key": "agent_type", "label": "Agent type", "type_id": "text"},
    {"key": "status", "label": "Status", "type_id": "text"},
    {"key": "task", "label": "Task", "type_id": "text"},
    {"key": "started_at", "label": "Started at", "type_id": "datetime"},
]


class GridStore:
    """An open handle to the grid persistence backend."""

    def __init__(
        self, sessionmaker: async_sessionmaker, *, embedded: Any = None
    ) -> None:
        self._sm = sessionmaker
        self._embedded = embedded

    @classmethod
    async def open(cls, database_url: str | None = None) -> "GridStore":
        from forktex_core.database import connection

        embedded = None
        url = database_url or runtime.derive_database_url()
        if url is None:
            url, embedded = _embedded_url()
        sessionmaker = connection.init_engine(url)
        assert connection.engine is not None
        await apply_migrations(connection.engine, schema=_SCHEMA)
        return cls(sessionmaker, embedded=embedded)

    async def close(self) -> None:
        from forktex_core.database import connection

        await connection.close_engine()
        if self._embedded is not None:
            self._embedded.cleanup()

    async def ensure_table(
        self, *, namespace: str, slug: str, label: str, columns: list[dict[str, Any]]
    ) -> None:
        """Provision a domain table in a namespace, idempotently."""
        async with self._sm() as session:
            try:
                await get_table(session, slug=slug, namespace=namespace)
                return
            except NotFoundError:
                table = await create_table(
                    session, slug=slug, label=label, namespace=namespace
                )
                for col in columns:
                    await create_column(session, table=table, **col)
                await session.commit()

    async def put(self, *, namespace: str, slug: str, values: dict[str, Any]) -> str:
        async with self._sm() as session:
            table = await get_table(session, slug=slug, namespace=namespace)
            row = await create_row(session, table=table, values=values)
            await session.commit()
            return str(row.id)

    async def query(
        self,
        *,
        namespace: str,
        slug: str,
        filter: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        async with self._sm() as session:
            table = await get_table(session, slug=slug, namespace=namespace)
            result = await query_rows(session, table=table, filter=filter, **kwargs)
            return [{"id": str(r.id), **r.payload} for r in result.rows]


# ── Domain helpers (namespace-aware) ─────────────────────────────────────────


async def register_project(
    store: GridStore, *, fingerprint: str, name: str, root: str
) -> str:
    await store.ensure_table(
        namespace=domains.SYSTEM,
        slug="project",
        label="Projects",
        columns=PROJECT_COLUMNS,
    )
    return await store.put(
        namespace=domains.SYSTEM,
        slug="project",
        values={"fingerprint": fingerprint, "name": name, "root": root},
    )


async def list_projects(store: GridStore) -> list[dict[str, Any]]:
    return await store.query(namespace=domains.SYSTEM, slug="project")


async def record_agent_run(
    store: GridStore, *, fingerprint: str, run: dict[str, Any]
) -> str:
    namespace = domains.project_ns(fingerprint)
    await store.ensure_table(
        namespace=namespace,
        slug="agent_run",
        label="Agent runs",
        columns=AGENT_RUN_COLUMNS,
    )
    return await store.put(namespace=namespace, slug="agent_run", values=run)


async def list_agent_runs(
    store: GridStore, *, fingerprint: str, **kwargs: Any
) -> list[dict[str, Any]]:
    return await store.query(
        namespace=domains.project_ns(fingerprint), slug="agent_run", **kwargs
    )


def _embedded_url() -> tuple[str, Any]:
    import pgserver  # type: ignore[import-not-found]

    server = pgserver.get_server(tempfile.mkdtemp(prefix="forktex_grid_pg_"))  # type: ignore[reportPrivateImportUsage]
    return server.get_uri().replace("postgresql://", "postgresql+asyncpg://"), server


__all__ = [
    "GridStore",
    "PROJECT_COLUMNS",
    "AGENT_RUN_COLUMNS",
    "register_project",
    "list_projects",
    "record_agent_run",
    "list_agent_runs",
]
