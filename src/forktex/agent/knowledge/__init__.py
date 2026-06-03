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

"""``forktex.agent.knowledge`` — the runtime surface over the fractal knowledge engine.

``forktex_core.fractal`` is the slim, domain-neutral substrate (typed multigraph,
compose, query, retrieve). The *agent-facing* surface lives here in forktex-py:

  - ``sources``    — consumer loaders (a docs repo → a fractal Workspace) + a
                     composing ``KnowledgeResolver`` (global docs + project overlay).
  - ``tools``      — a forktex ``Tool`` catalog over ``FractalQuery``.
  - ``cli``        — ``forktex knowledge`` (ask / show / list).
  - ``mcp_server`` — ``forktex mcp`` (MCP stdio) so Claude Code / Codex can query
                     live knowledge mid-task.
"""

from forktex.agent.knowledge.sources import (
    KnowledgeResolver,
    build_knowledge_resolver,
    load_docs_corpus,
)
from forktex.agent.knowledge.tools import build_knowledge_tools

__all__ = [
    "KnowledgeResolver",
    "build_knowledge_resolver",
    "build_knowledge_tools",
    "load_docs_corpus",
]
