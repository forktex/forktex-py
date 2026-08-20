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

"""Tests for ``ForktexManifest`` per-env overlay loader (§X)."""

from __future__ import annotations

import json
from pathlib import Path

# Import order matters: load fsd first to break a known cold-start
# circular import between forktex.fsd.loader and forktex.manifest.models.
import forktex.fsd  # noqa: F401  (warms up the chain)

from forktex.manifest._overlay import deep_merge
from forktex.manifest.models import ForktexManifest


# ── deep_merge ────────────────────────────────────────────────────────────


def test_deep_merge_scalar_overlay_wins():
    base = {"a": 1, "b": "old", "c": True}
    overlay = {"b": "new", "c": False}
    assert deep_merge(base, overlay) == {"a": 1, "b": "new", "c": False}


def test_deep_merge_nested_dict_recurses():
    base = {"cloud": {"deployment": {"replicas": 1, "memory": "512m"}}}
    overlay = {"cloud": {"deployment": {"replicas": 3}}}
    merged = deep_merge(base, overlay)
    assert merged == {"cloud": {"deployment": {"replicas": 3, "memory": "512m"}}}


def test_deep_merge_list_of_records_by_id_key():
    base = {"services": [{"id": "api", "port": 8000}, {"id": "web", "port": 80}]}
    overlay = {"services": [{"id": "api", "port": 9000}, {"id": "worker", "port": 0}]}
    merged = deep_merge(base, overlay)
    assert merged["services"] == [
        {"id": "api", "port": 9000},
        {"id": "web", "port": 80},
        {"id": "worker", "port": 0},
    ]


def test_deep_merge_list_of_records_by_name_key():
    base = {"environments": [{"name": "local"}, {"name": "prod"}]}
    overlay = {"environments": [{"name": "local", "provider": "compose"}]}
    merged = deep_merge(base, overlay)
    assert merged["environments"] == [
        {"name": "local", "provider": "compose"},
        {"name": "prod"},
    ]


def test_deep_merge_plain_list_replaces():
    base = {"tags": ["a", "b", "c"]}
    overlay = {"tags": ["x", "y"]}
    assert deep_merge(base, overlay) == {"tags": ["x", "y"]}


def test_deep_merge_overlay_only_keys_added():
    base = {"a": 1}
    overlay = {"b": 2}
    assert deep_merge(base, overlay) == {"a": 1, "b": 2}


def test_deep_merge_does_not_mutate_inputs():
    base = {"cloud": {"deployment": {"replicas": 1}}}
    overlay = {"cloud": {"deployment": {"replicas": 3}}}
    deep_merge(base, overlay)
    assert base == {"cloud": {"deployment": {"replicas": 1}}}
    assert overlay == {"cloud": {"deployment": {"replicas": 3}}}


# ── ForktexManifest.load(env=) ────────────────────────────────────────────


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload))


def _base_manifest(name: str = "test-project") -> dict:
    return {
        "manifestVersion": "1.0.0",
        "name": name,
        "packages": [
            {
                "name": "test-project",
                "path": ".",
                "version": "0.1.0",
                "publishable": True,
                "language": "python",
            }
        ],
    }


def test_manifest_load_no_env_loads_base(tmp_path):
    base_path = tmp_path / "forktex.json"
    _write(base_path, _base_manifest())
    m = ForktexManifest.load(base_path)
    assert m.name == "test-project"


def test_manifest_load_env_with_no_overlay_is_noop(tmp_path):
    """env="staging" but no forktex.staging.json — base manifest only."""
    base_path = tmp_path / "forktex.json"
    _write(base_path, _base_manifest())
    m = ForktexManifest.load(base_path, env="staging")
    assert m.name == "test-project"


def test_manifest_load_env_overlays_scalars(tmp_path):
    base_path = tmp_path / "forktex.json"
    _write(base_path, {**_base_manifest("base-name"), "description": "base desc"})
    overlay_path = tmp_path / "forktex.local.json"
    _write(overlay_path, {"description": "local desc"})

    m = ForktexManifest.load(base_path, env="local")
    assert m.name == "base-name"
    assert m.description == "local desc"


def test_manifest_load_env_merges_packages_by_name(tmp_path):
    base_path = tmp_path / "forktex.json"
    base = _base_manifest()
    base["packages"].append(
        {
            "name": "extra",
            "path": "extra",
            "version": "0.1.0",
            "publishable": False,
            "language": "python",
        }
    )
    _write(base_path, base)
    overlay_path = tmp_path / "forktex.local.json"
    _write(
        overlay_path,
        {
            "packages": [
                # bump the version of the existing test-project package
                {"name": "test-project", "version": "9.9.9"},
            ]
        },
    )

    m = ForktexManifest.load(base_path, env="local")
    by_name = {p.name: p for p in m.packages}
    assert by_name["test-project"].version == "9.9.9"
    assert by_name["extra"].version == "0.1.0"  # untouched


def test_manifest_load_env_does_not_mutate_base_file(tmp_path):
    base_path = tmp_path / "forktex.json"
    base = _base_manifest("immutable-base")
    _write(base_path, base)
    overlay_path = tmp_path / "forktex.local.json"
    _write(overlay_path, {"name": "overlayed"})

    ForktexManifest.load(base_path, env="local")

    # File on disk must be unchanged.
    on_disk = json.loads(base_path.read_text())
    assert on_disk["name"] == "immutable-base"
