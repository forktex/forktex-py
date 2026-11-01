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

import pytest

from forktex.error import BadRequestError, NotFoundError
from forktex.graph import (
    Graph,
    GraphEdge,
    GraphNode,
    InvalidDirectionError,
    NodeNotFoundError,
    edge_id,
)
from forktex.graph.models import GraphMeta


def _node(nid: str, kind: str = "person") -> GraphNode:
    return GraphNode(id=nid, kind=kind, name=nid)


def test_edge_id_is_deterministic_and_attrs_sensitive() -> None:
    a = edge_id("works_at", "alice", "acme", {"role": "eng"})
    b = edge_id("works_at", "alice", "acme", {"role": "eng"})
    c = edge_id("works_at", "alice", "acme", {"role": "pm"})
    assert a == b
    assert a != c


def test_add_node_is_idempotent() -> None:
    g = Graph.empty()
    n1 = g.add_node(_node("a"))
    n2 = g.add_node(_node("a"))
    assert n1 is n2
    assert len(g.nodes) == 1


def test_add_edge_collapses_identical_attrs_but_preserves_multi_edge() -> None:
    g = Graph.empty()
    g.add_node(_node("a"))
    g.add_node(_node("b"))
    e1 = g.add_edge("knows", "a", "b", {"since": 2020})
    e2 = g.add_edge("knows", "a", "b", {"since": 2020})
    e3 = g.add_edge("knows", "a", "b", {"since": 2024})
    e4 = g.add_edge("works_with", "a", "b", {"since": 2020})
    assert e1 is e2 or e1.id == e2.id
    assert e3.id != e1.id
    assert e4.id != e1.id
    assert len(g.edges) == 3


def test_add_edge_unknown_endpoint_raises() -> None:
    g = Graph.empty()
    g.add_node(_node("a"))
    with pytest.raises(KeyError):
        g.add_edge("knows", "a", "b")


def test_neighbors_directions() -> None:
    g = Graph.empty()
    for nid in ("a", "b", "c"):
        g.add_node(_node(nid))
    g.add_edge("knows", "a", "b")
    g.add_edge("knows", "b", "c")

    assert [n.id for n in g.neighbors("b", direction="out")] == ["c"]
    assert [n.id for n in g.neighbors("b", direction="in")] == ["a"]
    both = sorted(n.id for n in g.neighbors("b", direction="both"))
    assert both == ["a", "c"]


def test_neighbors_invalid_direction_raises() -> None:
    g = Graph.empty()
    g.add_node(_node("a"))
    with pytest.raises(ValueError):
        g.neighbors("a", direction="diagonal")


def test_lookups_after_parse_lazy_index() -> None:
    g_in = Graph.empty(GraphMeta(name="t"))
    for nid in ("a", "b"):
        g_in.add_node(_node(nid))
    g_in.add_edge("knows", "a", "b")
    payload = g_in.model_dump()
    g_parsed = Graph.model_validate(payload)
    assert g_parsed.has_node("a")
    assert [n.id for n in g_parsed.neighbors("a")] == ["b"]


def test_sorted_round_trip_is_byte_stable() -> None:
    g1 = Graph.empty(GraphMeta(name="t"))
    for nid in ("b", "a", "c"):
        g1.add_node(_node(nid))
    g1.add_edge("knows", "b", "c")
    g1.add_edge("knows", "a", "b")

    g2 = Graph.empty(GraphMeta(name="t"))
    for nid in ("a", "b", "c"):
        g2.add_node(_node(nid))
    g2.add_edge("knows", "a", "b")
    g2.add_edge("knows", "b", "c")

    s1 = g1.sorted().model_dump_json()
    s2 = g2.sorted().model_dump_json()
    assert s1 == s2


def test_merge_combines_nodes_and_edges() -> None:
    a = Graph.empty()
    a.add_node(_node("x"))
    a.add_node(_node("y"))
    a.add_edge("knows", "x", "y")

    b = Graph.empty()
    b.add_node(_node("y"))
    b.add_node(_node("z"))
    b.add_edge("knows", "y", "z")

    a.merge(b)
    assert sorted(n.id for n in a.nodes) == ["x", "y", "z"]
    assert {(e.kind, e.src_id, e.dst_id) for e in a.edges} == {
        ("knows", "x", "y"),
        ("knows", "y", "z"),
    }


def test_sorted_result_is_independent_of_source() -> None:
    g = Graph.empty()
    g.add_node(GraphNode(id="a", kind="n", attrs={"count": 1}))

    snapshot = g.sorted()
    snapshot.node("a").attrs["count"] = 999

    assert g.node("a").attrs["count"] == 1


def test_merge_result_is_independent_of_other() -> None:
    a = Graph.empty()
    a.add_node(GraphNode(id="x", kind="n", attrs={"count": 1}))

    b = Graph.empty()
    b.add_node(GraphNode(id="y", kind="n", attrs={"count": 1}))

    a.merge(b)
    a.node("x").attrs["count"] = 999
    a.node("y").attrs["count"] = 999

    assert b.node("y").attrs["count"] == 1


def test_from_iterables_constructs_graph() -> None:
    nodes = [_node("a"), _node("b")]
    edges = [
        GraphEdge(
            id=edge_id("knows", "a", "b"),
            kind="knows",
            src_id="a",
            dst_id="b",
        )
    ]
    g = Graph.from_iterables(nodes, edges)
    assert g.has_node("a")
    assert [n.id for n in g.neighbors("a")] == ["b"]


def test_by_kind_filters() -> None:
    g = Graph.empty()
    g.add_node(_node("a", kind="person"))
    g.add_node(_node("b", kind="person"))
    g.add_node(_node("c", kind="account"))
    g.add_edge("knows", "a", "b")
    g.add_edge("owns", "a", "c")

    persons = sorted(n.id for n in g.by_kind("person"))
    assert persons == ["a", "b"]
    knows = g.edges_by_kind("knows")
    assert len(knows) == 1


def test_add_edge_to_a_missing_endpoint_is_catchable_as_either_documented_type() -> None:
    g = Graph()
    g.add_node(_node("a"))
    for kwargs in ({"src_id": "a", "dst_id": "ghost"}, {"src_id": "ghost", "dst_id": "a"}):
        for catchable in (NodeNotFoundError, NotFoundError, KeyError):
            with pytest.raises(catchable):
                g.add_edge("knows", **kwargs)


def test_an_unknown_direction_is_catchable_as_either_documented_type() -> None:
    g = Graph()
    g.add_node(_node("a"))
    for catchable in (InvalidDirectionError, BadRequestError, ValueError):
        with pytest.raises(catchable):
            g.neighbors("a", direction="sideways")
