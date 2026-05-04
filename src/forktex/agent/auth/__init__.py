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

"""Shared building blocks for per-service credential management.

The three services (cloud, intelligence, network) each register their own
``connect`` / ``disconnect`` commands built by
:func:`forktex.agent.auth.cli.build_facet_commands`. There is no standalone
``forktex auth`` group — the verbs live inside each service for full parity.

The top-level ``forktex status`` aggregator also lives here.
"""

from __future__ import annotations

from forktex.agent.auth.cli import (
    build_facet_commands,
    connect_cloud,
    connect_intelligence,
    connect_network,
    status_cmd,
)
from forktex.agent.auth.status import collect_auth_status
from forktex.agent.auth.types import AuthKind, AuthState, Facet

__all__ = [
    "build_facet_commands",
    "status_cmd",
    "connect_cloud",
    "connect_intelligence",
    "connect_network",
    "collect_auth_status",
    "AuthState",
    "Facet",
    "AuthKind",
]
