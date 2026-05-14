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

"""Pluggable agent driver protocol — reserved for Intelligence SDK implementations.

Today we only use the HTTP driver (backed by ``Intelligence``).
The protocol is defined here so a later local-model driver, shipped inside
``forktex_intelligence``, can plug into the root loop without changes to
``forktex-py``. This mirrors how ``forktex_cloud`` contributes non-HTTP code
(paths, manifest, bridge, scaffold) alongside its HTTP client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AgentResponse:
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


class AgentDriver(Protocol):
    """Minimal surface the root loop depends on.

    Implementations:
    - HTTP: ``forktex_intelligence.drivers.http.HttpAgentDriver`` (future home).
      Until the SDK exposes it, the root loop wires the chat REPL directly.
    - Local model: follow-up, entirely additive in ``forktex_intelligence``.
    """

    async def handle(self, user_input: str) -> AgentResponse:  # pragma: no cover
        ...
