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

"""Phase B: the grid-backed persistence adaptor + namespace isolation.

Runs against an ephemeral embedded Postgres (the ``pgserver`` wheel); skips
cleanly if the grid stack or pgserver isn't installed.
"""

from __future__ import annotations

import tempfile

import pytest
import pytest_asyncio

pytest.importorskip("forktex_core.grid")
pgserver = pytest.importorskip("pgserver")

from forktex.grid import persistence  # noqa: E402
from forktex.grid.persistence import GridStore  # noqa: E402


@pytest_asyncio.fixture
async def store():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="ftx_grid_test_"))
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://")
    s = await GridStore.open(database_url=url)
    try:
        yield s
    finally:
        await s.close()
        server.cleanup()


async def test_project_registry_in_system_namespace(store: GridStore) -> None:
    await persistence.register_project(
        store, fingerprint="aaaa", name="Alpha", root="/p/alpha"
    )
    await persistence.register_project(
        store, fingerprint="bbbb", name="Beta", root="/p/beta"
    )
    projects = await persistence.list_projects(store)
    assert {p["fingerprint"] for p in projects} == {"aaaa", "bbbb"}


async def test_agent_runs_are_namespace_isolated(store: GridStore) -> None:
    await persistence.record_agent_run(
        store,
        fingerprint="aaaa",
        run={"agent_id": "r1", "status": "completed", "task": "build"},
    )
    await persistence.record_agent_run(
        store,
        fingerprint="bbbb",
        run={"agent_id": "r2", "status": "running", "task": "audit"},
    )
    a_runs = await persistence.list_agent_runs(store, fingerprint="aaaa")
    b_runs = await persistence.list_agent_runs(store, fingerprint="bbbb")
    # Each project's runs live in its own namespace — no cross-leak.
    assert [r["agent_id"] for r in a_runs] == ["r1"]
    assert [r["agent_id"] for r in b_runs] == ["r2"]


async def test_agent_run_query_filter(store: GridStore) -> None:
    for i, status in enumerate(["running", "completed", "running"]):
        await persistence.record_agent_run(
            store, fingerprint="cccc", run={"agent_id": f"a{i}", "status": status}
        )
    running = await persistence.list_agent_runs(
        store,
        fingerprint="cccc",
        filter={"column": "status", "op": "eq", "value": "running"},
    )
    assert {r["agent_id"] for r in running} == {"a0", "a2"}


async def test_ensure_table_is_idempotent(store: GridStore) -> None:
    # Re-registering the same project domain must not raise (table already exists).
    await persistence.register_project(store, fingerprint="dddd", name="D", root="/d")
    await persistence.register_project(store, fingerprint="eeee", name="E", root="/e")
    assert len(await persistence.list_projects(store)) == 2
