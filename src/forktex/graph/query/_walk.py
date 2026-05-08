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

"""Internal walk helpers shared by the query primitives.

These keep the per-query files focused on shape-mapping rather than
edge-walking boilerplate. Not part of the public ``forktex.graph.query``
surface — import paths inside the query package only.
"""

from __future__ import annotations

from forktex.graph.models import EdgeKind, Graph, GraphNode, NodeKind


def neighbors_of_kind(
    graph: Graph,
    node_id: str,
    *,
    edge_kind: EdgeKind,
    neighbor_kind: NodeKind,
) -> list[GraphNode]:
    """Return outgoing neighbours filtered by both edge kind and node kind.

    The most repeated graph-walk in the query layer: "what ``domain``
    nodes does this ``package`` contain?", "what ``module`` nodes does
    this ``domain`` contain?". Saves four lines per call site.
    """
    return [
        n for n in graph.neighbors(node_id, kind=edge_kind) if n.kind == neighbor_kind
    ]


def first_parent_of_kind(
    graph: Graph,
    node_id: str,
    *,
    edge_kind: EdgeKind,
    parent_kind: NodeKind,
) -> GraphNode | None:
    """Return the first incoming-edge parent matching ``parent_kind``.

    Used by ``list_modules_in_domain`` and similar queries that need to
    walk back up to the containing package.
    """
    for edge in graph.in_edges(node_id, kind=edge_kind):
        parent = graph.node(edge.src_id)
        if parent is not None and parent.kind == parent_kind:
            return parent
    return None
