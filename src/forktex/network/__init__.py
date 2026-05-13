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

"""forktex.network — Re-exports from the standalone ``forktex_network`` SDK.

The friendly public name is ``NetWork``; ``NetworkClient`` is its
long-form alias (kept for back-compat with existing import sites).

Usage::

    from forktex.network import NetWork

    async with NetWork(base_url="https://network.forktex.com") as net:
        token = await net.login(email, password)

For standalone usage outside forktex-py: ``pip install forktex-network``.

This module mirrors the ``forktex.cloud`` and ``forktex.intelligence``
shims so ``from forktex.{cloud,intelligence,network} import …`` is a
symmetric public API across all three platforms.
"""

from forktex_network import (
    NetworkAPIError,
    NetworkClient,
)

# ``NetWork`` is the friendly public name. Sibling sdk-py 0.2.3+ ships
# the alias at the package root; older floors fall back to the
# long-form ``NetworkClient`` so ``from forktex.network import NetWork``
# always works. Drop this fallback once the floor is bumped past
# whichever release first publishes the alias.
try:
    from forktex_network import NetWork  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover — pre-alias SDK
    NetWork = NetworkClient

# forktex-py-side settings layer (where credentials live + how they're
# loaded / saved). Re-exported so callers don't have to know that the
# settings module lives under ``forktex.agent.network.settings``.
from forktex.agent.network.settings import (
    NetworkSettings,
    load_network_settings,
    save_network_global,
    save_network_project,
)

__all__ = [
    # High-level API — `NetWork` is canonical; `NetworkClient` is the alias.
    "NetWork",
    "NetworkClient",
    "NetworkAPIError",
    # Settings (forktex-py-side persistence layer).
    "NetworkSettings",
    "load_network_settings",
    "save_network_global",
    "save_network_project",
]
