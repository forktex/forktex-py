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

"""Project filesystem fingerprint — the stable identity behind ``project:{fp}``.

A reproducible hash of a project's *identity files* (manifest + lockfiles), not
its whole tree, so a project's grid namespace is stable across machines/paths
and drift (manifest/lock changes) is detectable for reconcile/heal. Pure +
deterministic.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Files that define a project's identity (presence-tolerant).
IDENTITY_FILES = (
    "forktex.json",
    "pyproject.toml",
    "poetry.lock",
    "package.json",
    "package-lock.json",
)


def fingerprint_components(root: Path) -> dict[str, Any]:
    """The transparent inputs to the fingerprint (name + per-file content hash)."""
    name = ""
    manifest = root / "forktex.json"
    if manifest.exists():
        try:
            name = json.loads(manifest.read_text()).get("name", "")
        except Exception:  # noqa: BLE001 — best-effort; a bad manifest just yields an empty name
            name = ""
    files: dict[str, str] = {}
    for filename in IDENTITY_FILES:
        path = root / filename
        if path.exists():
            files[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"name": name, "files": files}


def project_fingerprint(root: Path) -> str:
    """A stable 16-hex fingerprint of the project's identity files."""
    blob = json.dumps(fingerprint_components(root), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


__all__ = ["IDENTITY_FILES", "fingerprint_components", "project_fingerprint"]
