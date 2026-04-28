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

"""Network settings persistence — load/save NetworkSettings from .forktex/ files.

Mirrors the cloud/intelligence settings pattern. Schema fields:

- ``endpoint`` — base URL (e.g. ``https://network.forktex.com`` or ``http://localhost:9000``).
- ``jwt_token`` — captured on ``forktex network connect``; used as ``Authorization: Bearer``.
- ``principal_email`` — the email that produced the token (display-only).
- ``authenticated_at`` — ISO-8601 UTC timestamp of last successful auth.

Token refresh is out of scope: when the token expires, the status probe
surfaces ``reachable=False`` and the user re-runs ``forktex network connect``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from forktex_cloud import paths as _cloud_paths


@dataclass
class NetworkSettings:
    endpoint: Optional[str] = None
    jwt_token: Optional[str] = None
    principal_email: Optional[str] = None
    authenticated_at: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint and self.jwt_token)


def load_network_settings(
    project_root: Optional[Path | str] = None,
    **overrides: Any,
) -> NetworkSettings:
    """Resolve settings from (lowest → highest priority): global file, project
    file, env vars (``FORKTEX_NETWORK_ENDPOINT``, ``FORKTEX_NETWORK_JWT_TOKEN``),
    explicit overrides.
    """
    values: dict[str, Any] = {}

    gpath = _cloud_paths.global_network_file()
    if gpath.exists():
        values.update(_read_json(gpath))

    if project_root is not None:
        root = Path(project_root)
        ppath = _cloud_paths.project_network_file(root)
        if ppath.exists():
            values.update(_read_json(ppath))

    env_map = {
        "endpoint": "FORKTEX_NETWORK_ENDPOINT",
        "jwt_token": "FORKTEX_NETWORK_JWT_TOKEN",
    }
    for key, env_name in env_map.items():
        val = os.environ.get(env_name)
        if val is not None:
            values[key] = val

    for k, v in overrides.items():
        if v is not None:
            values[k] = v

    return NetworkSettings(
        **{k: v for k, v in values.items() if k in NetworkSettings.__dataclass_fields__}
    )


def save_network_global(settings: NetworkSettings) -> None:
    _cloud_paths.ensure_global_dir()
    path = _cloud_paths.global_network_file()
    path.write_text(json.dumps(_dump(settings), indent=2) + "\n")


def save_network_project(settings: NetworkSettings, project_root: Path) -> None:
    _cloud_paths.ensure_project_dirs(project_root)
    path = _cloud_paths.project_network_file(project_root)
    path.write_text(json.dumps(_dump(settings), indent=2) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError, OSError:
        return {}
    return data if isinstance(data, dict) else {}


def _dump(settings: NetworkSettings) -> dict[str, Any]:
    return {k: v for k, v in asdict(settings).items() if v is not None}
