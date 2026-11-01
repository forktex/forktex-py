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


from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forktex.graph.models import EdgeKind, Graph


def induced_subgraph(graph: Graph, node_ids: Iterable[str]) -> Graph:
    from forktex.graph.models import Graph as _Graph

    keep = {nid for nid in node_ids if graph.has_node(nid)}
    new_nodes = [n.model_copy(deep=True) for n in graph.nodes if n.id in keep]
    new_edges = [e.model_copy(deep=True) for e in graph.edges if e.src_id in keep and e.dst_id in keep]
    return _Graph(meta=graph.meta, nodes=new_nodes, edges=new_edges)


def subgraph_around(
    graph: Graph,
    start_id: str,
    *,
    max_depth: int = 1,
    edge_kind: EdgeKind | None = None,
    direction: str = "both",
) -> Graph:
    if not graph.has_node(start_id):
        from forktex.graph.models import Graph as _Graph

        return _Graph(meta=graph.meta, nodes=[], edges=[])
    if max_depth <= 0:
        return induced_subgraph(graph, [start_id])

    keep: set[str] = {start_id}
    frontier: set[str] = {start_id}
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for nid in frontier:
            for n in graph.neighbors(nid, kind=edge_kind, direction=direction):
                if n.id not in keep:
                    next_frontier.add(n.id)
        if not next_frontier:
            break
        keep.update(next_frontier)
        frontier = next_frontier
    return induced_subgraph(graph, keep)


__all__ = ["induced_subgraph", "subgraph_around"]
