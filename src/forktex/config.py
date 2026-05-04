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

"""
forktex.config - Application configuration using Pydantic.

Base settings for the forktex package. LLM-specific configuration
has moved to forktex.intelligence.config.

Supports:
- Environment variables with FORKTEX_ prefix
- ~/.forktex/config.toml file
- .forktex/config.json (project-level)
- Programmatic overrides
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel

from forktex_cloud import paths as _cloud_paths


def _load_toml_config() -> Dict[str, Any]:
    """Load configuration from the global config.toml if it exists."""
    config_path = _cloud_paths.global_config_file()
    if not config_path.exists():
        return {}
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _load_project_config(project_root: Optional[str]) -> Dict[str, Any]:
    """Load the project config.json from the project root if it exists."""
    if not project_root:
        return {}
    config_path = _cloud_paths.project_config_file(Path(project_root))
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class Settings(BaseModel):
    """Main application settings.

    This is the lightweight base configuration. LLM-specific settings
    (provider, model, api_key) are in forktex.intelligence.config.

    Resolution order:
    1. Explicit constructor args
    2. Environment variables (FORKTEX_ prefix)
    3. ~/.forktex/config.toml (global)
    4. .forktex/config.json (project-level)
    5. Defaults
    """

    # Debug mode
    debug: bool = False

    @classmethod
    def load(cls, project_root: Optional[str] = None, **overrides: Any) -> "Settings":
        """Load settings from all sources."""
        # Start with project-level config (lowest priority)
        project_cfg = _load_project_config(project_root)

        # Then global TOML config
        toml = _load_toml_config()

        # Build values dict: project -> toml -> env -> overrides
        values: Dict[str, Any] = {}

        # Project-level config values
        for key in cls.model_fields:
            if key in project_cfg:
                values[key] = project_cfg[key]

        # TOML values (override project config)
        for key in cls.model_fields:
            if key in toml:
                values[key] = toml[key]

        # Environment variables
        env_map = {
            "debug": ["FORKTEX_DEBUG"],
        }
        for field_name, env_names in env_map.items():
            for env_name in env_names:
                val = os.environ.get(env_name)
                if val is not None:
                    field_info = cls.model_fields[field_name]
                    if field_info.annotation is float:
                        values[field_name] = float(val)
                    elif field_info.annotation is int:
                        values[field_name] = int(val)
                    elif field_info.annotation is bool:
                        values[field_name] = val.lower() in ("1", "true", "yes")
                    else:
                        values[field_name] = val
                    break

        # Explicit overrides take precedence
        for k, v in overrides.items():
            if v is not None:
                values[k] = v

        return cls(**values)


# Cached global settings
_settings: Optional[Settings] = None


def get_settings(project_root: Optional[str] = None, **overrides: Any) -> Settings:
    """Get or create cached settings."""
    global _settings
    if _settings is None or overrides or project_root:
        _settings = Settings.load(project_root=project_root, **overrides)
    return _settings


def reset_settings() -> None:
    """Reset cached settings (for testing)."""
    global _settings
    _settings = None
