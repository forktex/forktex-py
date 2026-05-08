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

"""Typed multi-edge graph schema.

The graph is the source of truth for ForkTex architecture tooling. Nodes
describe filesystem-tangible artifacts (files, modules, packages, manifests,
``.forktex`` directories, registered projects) and language-level grouping
(domains, libraries). Edges are typed and can repeat between the same pair
of nodes with different kinds (multi-edge): for example a ``package`` may
both ``contain`` a ``domain`` and ``expose_via`` it.

The Pydantic envelope is the wire format. The ``Graph`` class additionally
maintains in-memory adjacency indices for O(1) neighbour lookups; these
indices are rebuilt lazily and never serialised.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Literal

from pydantic import Field, PrivateAttr

from forktex.models.base import ForkTexModel


# ── Type aliases ──────────────────────────────────────────────────────────

NodeKind = Literal[
    "project_root",
    "forktex_dir",
    "manifest",
    "package",
    "domain",
    "module",
    "file",
    "library",
    "external_dep",
    "service",
    "registered_project",
]

EdgeKind = Literal[
    "contains",
    "imports",
    "depends_on",
    "exposes_via",
    "scaffolded_by",
    "registered_in",
    "manifest_of",
    "writes_to",
    "owns",
    "publishes",
]

Scope = Literal["project", "os"]

NODE_KINDS: tuple[str, ...] = (
    "project_root",
    "forktex_dir",
    "manifest",
    "package",
    "domain",
    "module",
    "file",
    "library",
    "external_dep",
    "service",
    "registered_project",
)

EDGE_KINDS: tuple[str, ...] = (
    "contains",
    "imports",
    "depends_on",
    "exposes_via",
    "scaffolded_by",
    "registered_in",
    "manifest_of",
    "writes_to",
    "owns",
    "publishes",
)


# ── Models ────────────────────────────────────────────────────────────────


class GraphMeta(ForkTexModel):
    """Single source of truth for export-time metadata.

    ``generated_at`` propagates to every export format (json/dsl/html) so all
    three artifacts share one timestamp.
    """

    generated_at: str
    scope: Scope
    root: str
    schema_version: int = 1


class GraphNode(ForkTexModel):
    """A typed graph node."""

    id: str
    kind: NodeKind
    name: str
    scope: Scope
    attrs: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(ForkTexModel):
    """A typed graph edge.

    The ``id`` is computed from ``(kind, src_id, dst_id, attrs)`` so any two
    edges with the same shape collapse, while edges that differ in kind or
    attributes coexist between the same node pair (multi-edge).
    """

    id: str
    kind: EdgeKind
    src_id: str
    dst_id: str
    attrs: dict[str, Any] = Field(default_factory=dict)


def edge_id(kind: str, src_id: str, dst_id: str, attrs: dict[str, Any]) -> str:
    """Deterministic edge id including a short hash of attrs."""
    h = hashlib.blake2s(
        json.dumps(attrs, sort_keys=True, default=str).encode("utf-8"),
        digest_size=4,
    ).hexdigest()
    return f"{kind}:{src_id}->{dst_id}:{h}"


class Graph(ForkTexModel):
    """Typed multi-edge graph with deterministic serialisation.

    Adjacency indices (``_by_id``, ``_out``, ``_in``) are private and
    excluded from serialisation. They are rebuilt on demand.
    """

    meta: GraphMeta
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    _by_id: dict[str, GraphNode] = PrivateAttr(default_factory=dict)
    _out: dict[str, list[GraphEdge]] = PrivateAttr(default_factory=dict)
    _in: dict[str, list[GraphEdge]] = PrivateAttr(default_factory=dict)
    _indexed: bool = PrivateAttr(default=False)

    # ── Mutation ────────────────────────────────────────────────────────

    def add_node(self, node: GraphNode) -> GraphNode:
        if node.id in self._by_id:
            return self._by_id[node.id]
        self.nodes.append(node)
        self._by_id[node.id] = node
        self._out.setdefault(node.id, [])
        self._in.setdefault(node.id, [])
        return node

    def add_edge(
        self,
        kind: EdgeKind,
        src_id: str,
        dst_id: str,
        attrs: dict[str, Any] | None = None,
    ) -> GraphEdge:
        attrs = attrs or {}
        eid = edge_id(kind, src_id, dst_id, attrs)
        if any(e.id == eid for e in self.edges):
            return next(e for e in self.edges if e.id == eid)
        edge = GraphEdge(id=eid, kind=kind, src_id=src_id, dst_id=dst_id, attrs=attrs)
        self.edges.append(edge)
        self._out.setdefault(src_id, []).append(edge)
        self._in.setdefault(dst_id, []).append(edge)
        return edge

    # ── Lookup ──────────────────────────────────────────────────────────

    def _ensure_index(self) -> None:
        if self._indexed:
            return
        self._by_id.clear()
        self._out.clear()
        self._in.clear()
        for n in self.nodes:
            self._by_id[n.id] = n
            self._out.setdefault(n.id, [])
            self._in.setdefault(n.id, [])
        for e in self.edges:
            self._out.setdefault(e.src_id, []).append(e)
            self._in.setdefault(e.dst_id, []).append(e)
        self._indexed = True

    def node(self, node_id: str) -> GraphNode | None:
        self._ensure_index()
        return self._by_id.get(node_id)

    def out_edges(
        self, node_id: str, *, kind: EdgeKind | None = None
    ) -> list[GraphEdge]:
        self._ensure_index()
        edges = self._out.get(node_id, [])
        return [e for e in edges if kind is None or e.kind == kind]

    def in_edges(
        self, node_id: str, *, kind: EdgeKind | None = None
    ) -> list[GraphEdge]:
        self._ensure_index()
        edges = self._in.get(node_id, [])
        return [e for e in edges if kind is None or e.kind == kind]

    def neighbors(
        self, node_id: str, *, kind: EdgeKind | None = None
    ) -> list[GraphNode]:
        self._ensure_index()
        return [
            self._by_id[e.dst_id]
            for e in self.out_edges(node_id, kind=kind)
            if e.dst_id in self._by_id
        ]

    def by_kind(self, kind: NodeKind) -> list[GraphNode]:
        return [n for n in self.nodes if n.kind == kind]

    def edges_by_kind(self, kind: EdgeKind) -> list[GraphEdge]:
        return [e for e in self.edges if e.kind == kind]

    # ── Serialisation ────────────────────────────────────────────────────

    def sorted(self) -> "Graph":
        """Return a new Graph with deterministically sorted nodes and edges.

        Required before writing ``graph.json`` so the file is byte-stable
        across runs (same input → same output → no diff churn).
        """
        sorted_nodes = sorted(self.nodes, key=lambda n: n.id)
        sorted_edges = sorted(
            self.edges, key=lambda e: (e.kind, e.src_id, e.dst_id, e.id)
        )
        return Graph(meta=self.meta, nodes=sorted_nodes, edges=sorted_edges)

    def merge(self, other: "Graph") -> "Graph":
        """Merge ``other`` into self (mutating). Meta of self is kept."""
        for n in other.nodes:
            self.add_node(n)
        for e in other.edges:
            self.add_edge(e.kind, e.src_id, e.dst_id, e.attrs)
        return self

    # ── Convenience constructors ────────────────────────────────────────

    @classmethod
    def empty(cls, meta: GraphMeta) -> "Graph":
        return cls(meta=meta, nodes=[], edges=[])

    @classmethod
    def from_iterables(
        cls,
        meta: GraphMeta,
        nodes: Iterable[GraphNode],
        edges: Iterable[GraphEdge],
    ) -> "Graph":
        g = cls.empty(meta)
        for n in nodes:
            g.add_node(n)
        for e in edges:
            g.add_edge(e.kind, e.src_id, e.dst_id, e.attrs)
        return g
