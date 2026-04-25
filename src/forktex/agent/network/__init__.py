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

"""forktex.agent.network — Network facet (forktex-network SDK integration).

Exposes a ``forktex network`` CLI group (status-only in V1) and a thin
settings layer mirroring the cloud/intelligence pattern.
"""

from __future__ import annotations

from forktex.agent.network.cli import network
from forktex.agent.network.settings import (
    NetworkSettings,
    load_network_settings,
    save_network_global,
    save_network_project,
)

__all__ = [
    "network",
    "NetworkSettings",
    "load_network_settings",
    "save_network_global",
    "save_network_project",
]
