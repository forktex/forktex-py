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
Forktex - Python SDK

pip install forktex

Includes:
- Core: state management, utilities, config
- Intelligence: agentic AI via Intelligence API (also available standalone: pip install forktex-intelligence)
- Cloud: infrastructure management
- Agent: CLI and interactive tools

Quick Start:
    from forktex.core.state import StateManager
    from forktex_intelligence import Intelligence
    from forktex_cloud.client import ForktexCloudClient

CLI:
    forktex chat
"""

__version__ = "0.2.3"
__author__ = "Forktex Team"

# Core library exports — always available, no optional deps
from forktex.core.state import StateManager
from forktex.core.utils import generate_id, current_timestamp
from forktex.core.paths import (
    get_global_config_dir,
    get_project_config_dir,
    ensure_global_config_dir,
    ensure_project_config_dir,
)
from forktex.config import Settings, get_settings

__all__ = [
    "__version__",
    # Core
    "StateManager",
    "generate_id",
    "current_timestamp",
    "get_global_config_dir",
    "get_project_config_dir",
    "ensure_global_config_dir",
    "ensure_project_config_dir",
    # Config
    "Settings",
    "get_settings",
]
