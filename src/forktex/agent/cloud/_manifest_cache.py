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

"""Per-process cache for parsed ``forktex.json`` manifests.

``forktex cloud up`` and friends call ``Manifest.load`` 3–4 times in
the same command path — once to render the compose file, again to
extract the project name, again for the print-port-table helper, etc.
That's 4 disk reads + 4 Pydantic round-trips for unchanged content.

This module caches the parsed object keyed by ``(project_root,
env_name)``, with mtime-based invalidation so writes through
``tracked_write`` are picked up on the next call.

The cache is per-process and not shared across `forktex` invocations
(every CLI call gets a fresh process). That keeps the contract
simple: never returns stale data within a single command, never
cross-pollutes between commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


__all__ = ["load_manifest", "clear"]


_CACHE: dict[tuple[str, str | None], tuple[float, Any]] = {}


def load_manifest(project_root: Path, *, env: str | None = "local") -> Any:
    """Return ``forktex_cloud.manifest.loader.Manifest`` for *project_root*.

    Cached per ``(project_root, env)`` keyed on the manifest file's
    mtime; reloads automatically when the file is rewritten by
    ``forktex cloud init`` or any ``tracked_write``.
    """

    from forktex_cloud.manifest.loader import Manifest

    manifest_path = project_root / "forktex.json"
    key = (str(project_root.resolve()), env)
    try:
        mtime = manifest_path.stat().st_mtime_ns / 1e9
    except FileNotFoundError:
        # Let the SDK raise its native error; don't smuggle a custom one.
        return Manifest.load(manifest_path, env=env)
    cached = _CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    manifest = Manifest.load(manifest_path, env=env)
    _CACHE[key] = (mtime, manifest)
    return manifest


def clear() -> None:
    """Drop every cached entry (used by tests + ``cloud init`` flows)."""
    _CACHE.clear()
