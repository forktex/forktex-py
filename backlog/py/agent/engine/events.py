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

"""Engine event vocabulary — the single swap-seam.

The agent loop and its consumers speak ``AgentEvent`` / ``AgentEventType``.
Today these alias the ``forktex_intelligence`` SSE types — the wire format every
consumer already uses, so aliasing avoids churn at each call site. The provider
adapter (``agent/intelligence/provider.py``) yields these already-parsed.

If the engine ever owns its own event model, **this module is the only place to
swap**: redefine ``AgentEvent``/``AgentEventType`` here and translate at the
provider boundary; the loop and consumers are unaffected.
"""

from __future__ import annotations

from forktex_intelligence import SSEEvent as AgentEvent
from forktex_intelligence import SSEEventType as AgentEventType

__all__ = ["AgentEvent", "AgentEventType"]
