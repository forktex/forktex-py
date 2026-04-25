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

"""forktex.core - Core utilities, state management, and path resolution."""

from forktex.core.utils import generate_id, current_timestamp
from forktex.core.state import StateManager
from forktex.core.paths import (
    get_global_config_dir,
    get_project_config_dir,
    ensure_global_config_dir,
    ensure_project_config_dir,
    get_global_config_file,
    get_project_config_file,
)

__all__ = [
    "generate_id",
    "current_timestamp",
    "StateManager",
    "get_global_config_dir",
    "get_project_config_dir",
    "ensure_global_config_dir",
    "ensure_project_config_dir",
    "get_global_config_file",
    "get_project_config_file",
]
