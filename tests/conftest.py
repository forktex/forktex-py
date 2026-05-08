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

"""Test fixtures."""

import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_dir_with_files(temp_dir):
    """Create a temporary directory with sample files."""
    # Create some files
    (Path(temp_dir) / "main.py").write_text("print('hello')\n")
    (Path(temp_dir) / "utils.py").write_text("def add(a, b):\n    return a + b\n")
    (Path(temp_dir) / "README.md").write_text("# Test Project\n")
    sub = Path(temp_dir) / "src"
    sub.mkdir()
    (sub / "app.py").write_text("from utils import add\n")
    (sub / "__init__.py").write_text("")
    return temp_dir


@pytest.fixture
def temp_git_repo(temp_dir):
    """Create a temporary git repository."""
    import subprocess

    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=temp_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=temp_dir, capture_output=True
    )
    (Path(temp_dir) / "file.txt").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=temp_dir, capture_output=True
    )
    return temp_dir


# ── Isolation fixtures for the OS fingerprint surface ─────────────────────


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch, request):
    """Redirect ``Path.home()`` (and therefore ``forktex_cloud.paths.global_dir``)
    to a tmp directory so the real ``~/.forktex/`` is never touched.

    Autouse so every test in the suite is sandboxed by default — pre-existing
    tests that exercise ``tracked_write`` (cloud/intelligence/network settings,
    state writes) no longer leak into the production registry.

    Tests that genuinely need the real HOME (e.g., would re-read live cloud
    creds) can opt out with ``@pytest.mark.real_home``.

    Drains ``forktex.runtime.lifecycle._active_instances`` at teardown — any
    instance the test created would otherwise have its close record written
    by the process-wide ``atexit`` handler AFTER ``monkeypatch`` restored
    ``HOME``, leaking into the production registry.
    """
    if "real_home" in request.keywords:
        yield None
        return
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("APPDATA", str(home))
    monkeypatch.delenv("FORKTEX_STRUCTURE_LENIENT", raising=False)
    try:
        yield home
    finally:
        try:
            from forktex.runtime import lifecycle as _lifecycle

            _lifecycle._active_instances.clear()
        except Exception:
            pass


@pytest.fixture
def project_root(tmp_path):
    """Create a minimal project tree with ``forktex.json`` and an empty
    ``.forktex/`` directory."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "forktex.json").write_text(
        '{"manifestVersion":"1.0.0","name":"proj","version":"0.0.1"}\n'
    )
    (root / ".forktex").mkdir()
    (root / ".forktex" / ".version").write_text("1\n")
    return root


@pytest.fixture
def monorepo_root(tmp_path):
    """Create a monorepo with nested ``forktex.json`` files and ``.forktex``
    directories at multiple depths.

    Layout::

        repo/
        ├── forktex.json
        ├── .forktex/.version
        ├── packages/api/forktex.json
        ├── packages/api/.forktex/.version
        └── packages/web/forktex.json
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "forktex.json").write_text(
        '{"manifestVersion":"1.0.0","name":"repo","version":"0.0.1"}\n'
    )
    (root / ".forktex").mkdir()
    (root / ".forktex" / ".version").write_text("1\n")

    api = root / "packages" / "api"
    api.mkdir(parents=True)
    (api / "forktex.json").write_text(
        '{"manifestVersion":"1.0.0","name":"api","version":"0.0.1"}\n'
    )
    (api / ".forktex").mkdir()
    (api / ".forktex" / ".version").write_text("1\n")

    web = root / "packages" / "web"
    web.mkdir(parents=True)
    (web / "forktex.json").write_text(
        '{"manifestVersion":"1.0.0","name":"web","version":"0.0.1"}\n'
    )
    return root


@pytest.fixture
def orphan_dir(tmp_path):
    """A directory with no forktex.json anywhere above it."""
    d = tmp_path / "orphan"
    d.mkdir()
    return d


@pytest.fixture
def reset_audit_hook():
    """Reset the io_proxy audit-hook installation flag so a test can verify
    its installation in isolation. Idempotent: only flips it for the test."""
    from forktex.graph import io_proxy

    original = io_proxy._AUDIT_INSTALLED
    io_proxy._AUDIT_INSTALLED = False
    yield
    io_proxy._AUDIT_INSTALLED = original
