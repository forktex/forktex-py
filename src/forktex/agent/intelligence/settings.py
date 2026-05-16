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

"""Intelligence config persistence — load/save IntelligenceSettings from .forktex/ files.

IntelligenceSettings (from forktex_intelligence SDK) is a pure data model.
This module owns all filesystem I/O: reading config from environment variables,
``~/.forktex/intelligence.json`` (global), and ``<project>/.forktex/intelligence.json``
(project-level), and persisting changes back.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from forktex_cloud import paths as _cloud_paths
from forktex_intelligence import IntelligenceSettings

# Cached settings
_settings: Optional[IntelligenceSettings] = None


def load_intelligence_settings(
    project_root: Optional[str] = None,
    **overrides: Any,
) -> IntelligenceSettings:
    """Load intelligence settings from config files and env vars.

    Resolution order (highest priority first):
    1. Explicit overrides
    2. Environment variables (FORKTEX_INTELLIGENCE_ENDPOINT, FORKTEX_INTELLIGENCE_API_KEY)
    3. Project-level config (.forktex/intelligence.json)
    4. Global config (~/.forktex/intelligence.json)
    5. Defaults
    """
    values: dict[str, Any] = {}

    # Global config
    global_path = _cloud_paths.global_intelligence_file()
    if global_path.exists():
        try:
            data = json.loads(global_path.read_text())
            if isinstance(data, dict):
                for key in IntelligenceSettings.model_fields:
                    if key in data:
                        values[key] = data[key]
        except (json.JSONDecodeError, OSError):  # fmt: skip
            pass

    # Project-level config (overrides global)
    if project_root:
        from pathlib import Path as _P

        project_path = _cloud_paths.project_dir(_P(project_root)) / "intelligence.json"
        if project_path.exists():
            try:
                data = json.loads(project_path.read_text())
                if isinstance(data, dict):
                    for key in IntelligenceSettings.model_fields:
                        if key in data:
                            values[key] = data[key]
            except (json.JSONDecodeError, OSError):  # fmt: skip
                pass

    # Environment variables
    env_map = {
        "endpoint": "FORKTEX_INTELLIGENCE_ENDPOINT",
        "api_key": "FORKTEX_INTELLIGENCE_API_KEY",
    }
    for field_name, env_name in env_map.items():
        val = os.environ.get(env_name)
        if val is not None:
            values[field_name] = val

    # Explicit overrides
    for k, v in overrides.items():
        if v is not None:
            values[k] = v

    return IntelligenceSettings(**values)


def get_intelligence_settings(
    project_root: Optional[str] = None, **overrides: Any
) -> IntelligenceSettings:
    """Get or create cached intelligence settings."""
    global _settings
    if _settings is None or overrides or project_root:
        _settings = load_intelligence_settings(project_root=project_root, **overrides)
    return _settings


def reset_intelligence_settings() -> None:
    """Reset cached settings (for testing)."""
    global _settings
    _settings = None


def save_intelligence_global(settings: IntelligenceSettings) -> None:
    """Persist settings to the global intelligence config file."""
    from forktex.graph.io_proxy import tracked_write

    _cloud_paths.ensure_global_dir()
    path = _cloud_paths.global_intelligence_file()
    data = {"endpoint": settings.endpoint, "api_key": settings.api_key}
    tracked_write(
        path,
        json.dumps(data, indent=2) + "\n",
        kind="intelligence_settings",
        writer="forktex.agent.intelligence.settings",
    )


def save_intelligence_project(
    settings: IntelligenceSettings, project_root: str
) -> None:
    """Persist settings to the project intelligence config file."""
    from pathlib import Path as _P

    from forktex.graph.io_proxy import tracked_write

    _cloud_paths.ensure_project_dirs(_P(project_root))
    path = _cloud_paths.project_dir(_P(project_root)) / "intelligence.json"
    data = {"endpoint": settings.endpoint, "api_key": settings.api_key}
    tracked_write(
        path,
        json.dumps(data, indent=2) + "\n",
        kind="intelligence_settings",
        writer="forktex.agent.intelligence.settings",
    )
