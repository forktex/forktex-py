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

from collections import deque
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forktex.graph.models import EdgeKind, Graph


def bfs(
    graph: Graph,
    start_id: str,
    *,
    edge_kind: EdgeKind | None = None,
    direction: str = "out",
) -> list[str]:
    if not graph.has_node(start_id):
        return []
    visited: set[str] = {start_id}
    order: list[str] = [start_id]
    queue: deque[str] = deque([start_id])
    while queue:
        cur = queue.popleft()
        for n in graph.neighbors(cur, kind=edge_kind, direction=direction):
            if n.id not in visited:
                visited.add(n.id)
                order.append(n.id)
                queue.append(n.id)
    return order


def dfs(
    graph: Graph,
    start_id: str,
    *,
    edge_kind: EdgeKind | None = None,
    direction: str = "out",
) -> list[str]:
    if not graph.has_node(start_id):
        return []
    visited: set[str] = set()
    order: list[str] = []

    def _walk(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        order.append(node_id)
        for n in graph.neighbors(node_id, kind=edge_kind, direction=direction):
            _walk(n.id)

    _walk(start_id)
    return order


def transitive_closure(
    graph: Graph,
    start_id: str,
    *,
    edge_kind: EdgeKind | None = None,
    direction: str = "out",
) -> set[str]:
    return set(bfs(graph, start_id, edge_kind=edge_kind, direction=direction))


def shortest_path(
    graph: Graph,
    src_id: str,
    dst_id: str,
    *,
    edge_kind: EdgeKind | None = None,
    direction: str = "out",
) -> list[str] | None:
    if src_id == dst_id and graph.has_node(src_id):
        return [src_id]
    if not graph.has_node(src_id) or not graph.has_node(dst_id):
        return None
    parents: dict[str, str] = {}
    visited: set[str] = {src_id}
    queue: deque[str] = deque([src_id])
    found = False
    while queue and not found:
        cur = queue.popleft()
        for n in graph.neighbors(cur, kind=edge_kind, direction=direction):
            if n.id in visited:
                continue
            visited.add(n.id)
            parents[n.id] = cur
            if n.id == dst_id:
                found = True
                break
            queue.append(n.id)
    if not found:
        return None
    path = [dst_id]
    while path[-1] != src_id:
        path.append(parents[path[-1]])
    return list(reversed(path))


def cycles(
    graph: Graph,
    *,
    edge_kind: EdgeKind | None = None,
) -> list[list[str]]:

    def successors(nid: str) -> Iterable[str]:
        return [e.dst_id for e in graph.out_edges(nid, kind=edge_kind) if graph.has_node(e.dst_id)]

    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[list[str]] = []
    counter = [0]

    def _strongconnect(v: str) -> None:
        index_of[v] = counter[0]
        lowlink[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in successors(v):
            if w not in index_of:
                _strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index_of[w])
        if lowlink[v] == index_of[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for n in graph.nodes:
        if n.id not in index_of:
            _strongconnect(n.id)

    cyclic: list[list[str]] = []
    for comp in sccs:
        if len(comp) > 1:
            cyclic.append(comp)
        elif len(comp) == 1:
            v = comp[0]
            if any(e.dst_id == v for e in graph.out_edges(v, kind=edge_kind)):
                cyclic.append([v])
    return cyclic


__all__ = ["bfs", "cycles", "dfs", "shortest_path", "transitive_closure"]
