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

"""Construct a ``NetworkClient`` with credentials resolved from settings."""

from __future__ import annotations

from forktex_network import NetworkClient

from forktex.agent.network.settings import NetworkSettings


def build_network_client(settings: NetworkSettings) -> NetworkClient:
    """Return a ready-to-use async ``NetworkClient``.

    Callers own the lifecycle — remember to ``await client.close()`` or use
    the client as an async context manager.
    """
    if not settings.is_configured:
        raise RuntimeError(
            "network settings are not configured; run `forktex network connect` first."
        )
    assert settings.endpoint and settings.jwt_token  # for type-checkers
    return NetworkClient(base_url=settings.endpoint, jwt_token=settings.jwt_token)
