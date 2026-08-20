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

"""Reconcile the DB (source of truth) against the live filesystem.

The DB centralizes core info; the filesystem is only *referenced*. Drift happens
when a recorded project root disappears or its identity files change (so the
recomputed fingerprint no longer matches). ``reconcile_projects`` reports drift;
this is the basis for healing (re-link / re-fingerprint / prune).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forktex.grid import persistence
from forktex.grid.fingerprint import project_fingerprint


async def reconcile_projects(store: persistence.GridStore) -> dict[str, Any]:
    """Check every registered project's recorded root + fingerprint vs the FS."""
    projects = await persistence.list_projects(store)
    drifted: list[dict[str, str]] = []
    for project in projects:
        root = Path(project.get("root", ""))
        recorded = project.get("fingerprint", "")
        issue: str | None = None
        if not root.exists():
            issue = "root_missing"
        elif project_fingerprint(root) != recorded:
            issue = "fingerprint_drift"
        if issue:
            drifted.append({"fingerprint": recorded, "root": str(root), "issue": issue})
    return {
        "checked": len(projects),
        "healthy": len(projects) - len(drifted),
        "drifted": drifted,
    }


__all__ = ["reconcile_projects"]
