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

"""Tests for the per-process forktex.json manifest cache.

We mock ``Manifest.load`` to avoid coupling these tests to the
SDK's evolving manifest schema — the cache is the unit under test,
not the parser.
"""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from forktex.agent.cloud import _manifest_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    _manifest_cache.clear()
    yield
    _manifest_cache.clear()


@pytest.fixture
def fake_manifest(monkeypatch):
    """Replace ``Manifest.load`` with a counter that returns a fresh
    sentinel object each call. The cache should call us at most once
    per (root, env, mtime)."""
    calls: list[tuple[Path, str | None]] = []

    def _fake_load(path, *, env=None):
        calls.append((Path(path), env))
        return SimpleNamespace(name="demo", _call=len(calls))

    monkeypatch.setattr(
        "forktex_cloud.manifest.loader.Manifest.load", staticmethod(_fake_load)
    )
    return calls


def _write_manifest_stub(root: Path) -> Path:
    """Create an empty file just so ``stat`` succeeds; the parser is
    mocked, so content doesn't matter."""
    path = root / "forktex.json"
    path.write_text("{}\n")
    return path


def test_load_manifest_returns_object(tmp_path, fake_manifest):
    _write_manifest_stub(tmp_path)
    m = _manifest_cache.load_manifest(tmp_path, env="local")
    assert m.name == "demo"
    assert len(fake_manifest) == 1


def test_load_manifest_caches_same_call(tmp_path, fake_manifest):
    _write_manifest_stub(tmp_path)
    a = _manifest_cache.load_manifest(tmp_path, env="local")
    b = _manifest_cache.load_manifest(tmp_path, env="local")
    assert a is b
    assert len(fake_manifest) == 1, "second call should hit the cache"


def test_load_manifest_separate_envs_separate_entries(tmp_path, fake_manifest):
    _write_manifest_stub(tmp_path)
    a = _manifest_cache.load_manifest(tmp_path, env="local")
    b = _manifest_cache.load_manifest(tmp_path, env="prod")
    assert a is not b
    assert len(fake_manifest) == 2


def test_load_manifest_invalidates_on_mtime_change(tmp_path, fake_manifest):
    path = _write_manifest_stub(tmp_path)
    a = _manifest_cache.load_manifest(tmp_path, env="local")
    new_mtime = path.stat().st_mtime + 5
    os.utime(path, (new_mtime, new_mtime))
    b = _manifest_cache.load_manifest(tmp_path, env="local")
    assert a is not b
    assert len(fake_manifest) == 2


def test_clear_drops_all_entries(tmp_path, fake_manifest):
    _write_manifest_stub(tmp_path)
    a = _manifest_cache.load_manifest(tmp_path, env="local")
    _manifest_cache.clear()
    b = _manifest_cache.load_manifest(tmp_path, env="local")
    assert a is not b
    assert len(fake_manifest) == 2
