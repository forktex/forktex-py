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

"""Cloud context persistence — load/save CloudContext from .forktex/ files.

CloudContext (from forktex_cloud SDK) is a pure data model.  This module
owns all filesystem I/O: reading ``~/.forktex/cloud.json`` (global) and
``<project>/.forktex/cloud.json`` (project-level), merging them, and
persisting changes back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forktex_cloud import paths as _cloud_paths
from forktex_cloud.config import CloudContext


def load_cloud_context(project_root: Path | None = None) -> CloudContext:
    """Load cloud context, merging global + project-level configs.

    Resolution: project-level overrides global.
    """
    data: dict[str, Any] = {}

    # Global config
    global_path = _cloud_paths.global_cloud_file()
    if global_path.exists():
        try:
            data = json.loads(global_path.read_text())
        except json.JSONDecodeError, OSError:
            pass

    # Project-level config (overrides global)
    if project_root:
        project_path = _cloud_paths.project_dir(project_root) / "cloud.json"
        if project_path.exists():
            try:
                project_data = json.loads(project_path.read_text())
                data.update(project_data)
            except json.JSONDecodeError, OSError:
                pass

    return CloudContext(
        controller=data.get("controller"),
        account_key=data.get("account_key"),
        access_token=data.get("access_token"),
        org_id=data.get("org_id"),
        region=data.get("region"),
        project_keys=data.get("project_keys", {}),
        current_project=data.get("current_project"),
        current_server=data.get("current_server"),
        current_environment=data.get("current_environment"),
    )


def save_cloud_context_global(ctx: CloudContext) -> None:
    """Persist controller + credentials to the global cloud config file."""
    _cloud_paths.ensure_global_dir()
    path = _cloud_paths.global_cloud_file()
    data = {
        "controller": ctx.controller,
        "account_key": ctx.account_key,
        "access_token": ctx.access_token,
        "org_id": ctx.org_id,
        "region": ctx.region,
        "project_keys": ctx.project_keys,
    }
    path.write_text(json.dumps(data, indent=2) + "\n")


def save_cloud_context_project(ctx: CloudContext, project_root: Path) -> None:
    """Persist project-specific cloud state to the project cloud config file."""
    _cloud_paths.ensure_project_dirs(project_root)
    path = _cloud_paths.project_dir(project_root) / "cloud.json"
    data = {
        "current_project": ctx.current_project,
        "current_server": ctx.current_server,
        "current_environment": ctx.current_environment,
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
