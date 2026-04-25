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

"""Bare-``forktex`` interaction cycle.

Entry point for ``forktex`` (no subcommand). Renders a status-driven menu
that shows live auth state per facet, and auto-upgrades into the Intelligence
chat REPL when Intelligence is reachable. Menu-first today, agent-driven as
Intelligence SDK's driver module matures.
"""

from __future__ import annotations

from forktex.agent.root_loop.driver import AgentDriver, AgentResponse
from forktex.agent.root_loop.menu import run

__all__ = ["run", "AgentDriver", "AgentResponse"]
