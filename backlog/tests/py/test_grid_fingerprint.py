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

"""Phase C: project fingerprint (pure) + reconcile/heal (embedded PG)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

pytest.importorskip("forktex_core.grid")

from forktex.grid.fingerprint import project_fingerprint  # noqa: E402


def _write_project(root: Path, name: str = "demo") -> None:
    (root / "forktex.json").write_text(f'{{"manifestVersion":"1.0.0","name":"{name}"}}')
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n")


def test_fingerprint_is_deterministic(tmp_path: Path) -> None:
    _write_project(tmp_path)
    assert project_fingerprint(tmp_path) == project_fingerprint(tmp_path)
    assert len(project_fingerprint(tmp_path)) == 16


def test_fingerprint_changes_on_manifest_edit(tmp_path: Path) -> None:
    _write_project(tmp_path, name="one")
    before = project_fingerprint(tmp_path)
    _write_project(tmp_path, name="two")
    assert project_fingerprint(tmp_path) != before


def test_distinct_projects_distinct_fingerprints(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _write_project(a, name="alpha")
    _write_project(b, name="beta")
    assert project_fingerprint(a) != project_fingerprint(b)


# ── Reconcile against a real DB ───────────────────────────────────────────────

pgserver = pytest.importorskip("pgserver")

from forktex.grid import persistence  # noqa: E402
from forktex.grid.persistence import GridStore  # noqa: E402
from forktex.grid.reconcile import reconcile_projects  # noqa: E402


@pytest_asyncio.fixture
async def store():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="ftx_fp_test_"))
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://")
    s = await GridStore.open(database_url=url)
    try:
        yield s
    finally:
        await s.close()
        server.cleanup()


async def test_reconcile_flags_missing_root(store: GridStore, tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    _write_project(live)
    # Healthy project: recorded fingerprint matches the live tree.
    await persistence.register_project(
        store, fingerprint=project_fingerprint(live), name="live", root=str(live)
    )
    # Drifted project: recorded root does not exist.
    await persistence.register_project(
        store, fingerprint="dead0000", name="gone", root=str(tmp_path / "ghost")
    )

    report = await reconcile_projects(store)
    assert report["checked"] == 2
    assert report["healthy"] == 1
    assert report["drifted"][0]["issue"] == "root_missing"


async def test_reconcile_flags_fingerprint_drift(
    store: GridStore, tmp_path: Path
) -> None:
    live = tmp_path / "p"
    live.mkdir()
    _write_project(live, name="orig")
    await persistence.register_project(
        store, fingerprint=project_fingerprint(live), name="p", root=str(live)
    )
    _write_project(live, name="changed")  # mutate identity → fingerprint drift

    report = await reconcile_projects(store)
    assert report["drifted"][0]["issue"] == "fingerprint_drift"
