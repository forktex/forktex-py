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

from forktex.graph import (
    Graph,
    GraphNode,
    bfs,
    cycles,
    dfs,
    shortest_path,
    transitive_closure,
)


def _build_dag() -> Graph:
    g = Graph.empty()
    for nid in ("a", "b", "c", "d", "e"):
        g.add_node(GraphNode(id=nid, kind="n"))
    g.add_edge("k", "a", "b")
    g.add_edge("k", "b", "c")
    g.add_edge("k", "b", "d")
    g.add_edge("k", "d", "e")
    return g


def test_bfs_visits_in_order() -> None:
    g = _build_dag()
    order = bfs(g, "a")
    assert order[0] == "a"
    assert set(order) == {"a", "b", "c", "d", "e"}
    assert order.index("b") < order.index("c")
    assert order.index("b") < order.index("d")


def test_bfs_unknown_start_returns_empty() -> None:
    g = _build_dag()
    assert bfs(g, "nope") == []


def test_dfs_visits_full_reach() -> None:
    g = _build_dag()
    order = dfs(g, "a")
    assert order[0] == "a"
    assert set(order) == {"a", "b", "c", "d", "e"}


def test_transitive_closure_includes_self() -> None:
    g = _build_dag()
    closure = transitive_closure(g, "b")
    assert closure == {"b", "c", "d", "e"}


def test_transitive_closure_filters_by_edge_kind() -> None:
    g = _build_dag()
    g.add_node(GraphNode(id="x", kind="n"))
    g.add_edge("other_kind", "a", "x")
    assert "x" not in transitive_closure(g, "a", edge_kind="k")
    assert transitive_closure(g, "a", edge_kind="other_kind") == {"a", "x"}


def test_shortest_path_finds_unweighted_path() -> None:
    g = _build_dag()
    path = shortest_path(g, "a", "e")
    assert path == ["a", "b", "d", "e"]


def test_shortest_path_self_returns_singleton() -> None:
    g = _build_dag()
    assert shortest_path(g, "a", "a") == ["a"]


def test_shortest_path_disconnected_returns_none() -> None:
    g = _build_dag()
    g.add_node(GraphNode(id="lonely", kind="n"))
    assert shortest_path(g, "a", "lonely") is None


def test_shortest_path_unknown_endpoint_returns_none() -> None:
    g = _build_dag()
    assert shortest_path(g, "a", "ghost") is None
    assert shortest_path(g, "ghost", "a") is None


def test_bfs_dfs_cycles_on_empty_graph() -> None:
    g = Graph.empty()
    assert bfs(g, "anything") == []
    assert dfs(g, "anything") == []
    assert cycles(g) == []


def test_bfs_dfs_on_single_node_no_edges() -> None:
    g = Graph.empty()
    g.add_node(GraphNode(id="lonely", kind="n"))
    assert bfs(g, "lonely") == ["lonely"]
    assert dfs(g, "lonely") == ["lonely"]
    assert cycles(g) == []


def test_cycles_empty_for_dag() -> None:
    assert cycles(_build_dag()) == []


def test_cycles_finds_cycle_alongside_disconnected_acyclic_component() -> None:
    g = Graph.empty()
    for nid in ("a", "b", "c", "x", "y"):
        g.add_node(GraphNode(id=nid, kind="n"))
    g.add_edge("k", "a", "b")
    g.add_edge("k", "b", "c")
    g.add_edge("k", "c", "a")
    g.add_edge("k", "x", "y")
    found = cycles(g)
    assert len(found) == 1
    assert sorted(found[0]) == ["a", "b", "c"]


def test_cycles_detects_simple_cycle() -> None:
    g = Graph.empty()
    for nid in ("a", "b", "c"):
        g.add_node(GraphNode(id=nid, kind="n"))
    g.add_edge("k", "a", "b")
    g.add_edge("k", "b", "c")
    g.add_edge("k", "c", "a")
    found = cycles(g)
    assert len(found) == 1
    assert sorted(found[0]) == ["a", "b", "c"]


def test_cycles_detects_self_loop() -> None:
    g = Graph.empty()
    g.add_node(GraphNode(id="a", kind="n"))
    g.add_edge("k", "a", "a")
    assert cycles(g) == [["a"]]


def test_cycles_filtered_by_kind() -> None:
    g = Graph.empty()
    for nid in ("a", "b"):
        g.add_node(GraphNode(id=nid, kind="n"))
    g.add_edge("k1", "a", "b")
    g.add_edge("k2", "b", "a")
    assert cycles(g) != []
    assert cycles(g, edge_kind="k1") == []
    assert cycles(g, edge_kind="k2") == []
