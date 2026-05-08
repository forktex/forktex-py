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

"""Tests for SECURITY.md §A — `forktex clean --secure-perms`."""

import stat
import sys

import pytest

from forktex.agent.purge import _apply_secure_perms


pytestmark = [
    pytest.mark.usefixtures("isolated_home"),
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission test"),
]


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_secure_perms_tightens_project_secrets(project_root):
    fdir = project_root / ".forktex"
    intel = fdir / "intelligence.json"
    intel.write_text('{"endpoint":"x","api_key":"y"}')
    intel.chmod(0o644)
    network = fdir / "network.json"
    network.write_text('{"endpoint":"x","jwt":"y"}')
    network.chmod(0o644)
    safe = fdir / "config.json"  # config-tagged, not secret
    safe.write_text("{}")
    safe.chmod(0o644)

    tightened = _apply_secure_perms("project", project_root)

    assert intel in tightened
    assert network in tightened
    # config.json is sensitivity=config, not secret — should be ignored.
    assert safe not in tightened
    assert _mode(intel) == 0o600
    assert _mode(network) == 0o600
    assert _mode(safe) == 0o644


def test_secure_perms_handles_glob_patterns(project_root):
    fdir = project_root / ".forktex"
    keys_dir = fdir / "state" / "keys"
    keys_dir.mkdir(parents=True)
    k1 = keys_dir / "server-a.key"
    k1.write_text("PRIVATE")
    k1.chmod(0o644)
    k2 = keys_dir / "server-b.key"
    k2.write_text("PRIVATE")
    k2.chmod(0o644)

    tightened = _apply_secure_perms("project", project_root)

    assert k1 in tightened
    assert k2 in tightened
    assert _mode(k1) == 0o600
    assert _mode(k2) == 0o600


def test_secure_perms_handles_global_secrets(isolated_home, project_root):
    gdir = isolated_home / ".forktex"
    gdir.mkdir(exist_ok=True)
    cloud = gdir / "cloud.json"
    cloud.write_text('{"controller":"x","access_token":"y"}')
    cloud.chmod(0o644)

    tightened = _apply_secure_perms("os", project_root)

    assert cloud in tightened
    assert _mode(cloud) == 0o600


def test_secure_perms_idempotent(project_root):
    fdir = project_root / ".forktex"
    intel = fdir / "intelligence.json"
    intel.write_text("{}")
    intel.chmod(0o600)

    tightened = _apply_secure_perms("project", project_root)
    # Already 0o600 but we still report it as tightened (chmod is a no-op
    # but successful).
    assert intel in tightened
    assert _mode(intel) == 0o600


def test_secure_perms_returns_empty_when_no_secrets(project_root):
    """With no secret-tagged files present, nothing to tighten."""
    tightened = _apply_secure_perms("project", project_root)
    assert tightened == []
