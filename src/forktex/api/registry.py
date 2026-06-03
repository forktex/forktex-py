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

"""Assemble the forktex tool domains from the existing per-domain builders.

This is the one place that knows *which* tools forktex exposes — the same
:class:`Tool` objects the CLI verbs and the agent loop drive. The API/MCP
adapters consume this map; nothing here is HTTP- or MCP-specific (so it imports
without the ``[mcp]`` extra). New domains land by adding a builder entry.
"""

from __future__ import annotations

from pathlib import Path

from forktex.agent.tools.base import Tool


def build_domains(
    project_root: str | Path | None = None,
    *,
    read_only: bool = False,
) -> dict[str, list[Tool]]:
    """Return ``{domain: [Tool, …]}`` for the generic tool API.

    - ``knowledge`` — the substrate use-cases over the composed fractal
      (search/show/neighbors/list, + recycle/retire/rollup unless *read_only*).
    - ``arch`` — the structural-authority graph queries over the project graph.
    - ``fsd`` — the delivery-standard audit (per-atom pass/fail + level).

    ``read_only`` drops the knowledge write tools (recycle/retire/rollup) — the
    right default for an exposed/shared HTTP surface.
    """
    from forktex.agent.tools.catalog import build_group

    root = Path(project_root).resolve() if project_root else Path.cwd()
    # API domain → catalog tool group. Both adapters (this + the agent loop)
    # compose from the one catalog; nothing is defined twice.
    domain_groups = {"knowledge": "knowledge", "arch": "graph", "fsd": "fsd"}
    domains = {
        domain: build_group(group, root, read_only=read_only)
        for domain, group in domain_groups.items()
    }
    return {d: tools for d, tools in domains.items() if tools}


__all__ = ["build_domains"]
