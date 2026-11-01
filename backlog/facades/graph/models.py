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

import copy
import hashlib
import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from forktex.graph.errors import InvalidDirectionError, NodeNotFoundError

NodeKind = str
EdgeKind = str


class GraphMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    generated_at: str | None = None
    schema_version: int = 1


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    kind: NodeKind
    name: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    kind: EdgeKind
    src_id: str
    dst_id: str
    attrs: dict[str, Any] = Field(default_factory=dict)


def edge_id(kind: str, src_id: str, dst_id: str, attrs: dict[str, Any] | None = None) -> str:
    payload = json.dumps(attrs or {}, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.blake2s(payload, digest_size=4).hexdigest()
    return f"{kind}:{src_id}->{dst_id}:{digest}"


class Graph(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meta: GraphMeta = Field(default_factory=GraphMeta)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    _by_id: dict[str, GraphNode] = PrivateAttr(default_factory=dict)
    _out: dict[str, list[GraphEdge]] = PrivateAttr(default_factory=dict)
    _in: dict[str, list[GraphEdge]] = PrivateAttr(default_factory=dict)
    _edge_ids: set[str] = PrivateAttr(default_factory=set)
    _indexed: bool = PrivateAttr(default=False)

    def add_node(self, node: GraphNode) -> GraphNode:
        self._ensure_index()
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
        self._ensure_index()
        if src_id not in self._by_id:
            raise NodeNotFoundError(f"unknown src_id: {src_id!r}")
        if dst_id not in self._by_id:
            raise NodeNotFoundError(f"unknown dst_id: {dst_id!r}")
        attrs = attrs or {}
        eid = edge_id(kind, src_id, dst_id, attrs)
        if eid in self._edge_ids:
            return next(e for e in self.edges if e.id == eid)
        edge = GraphEdge(id=eid, kind=kind, src_id=src_id, dst_id=dst_id, attrs=attrs)
        self.edges.append(edge)
        self._edge_ids.add(eid)
        self._out.setdefault(src_id, []).append(edge)
        self._in.setdefault(dst_id, []).append(edge)
        return edge

    def _ensure_index(self) -> None:
        if self._indexed:
            return
        self._by_id.clear()
        self._out.clear()
        self._in.clear()
        self._edge_ids.clear()
        for n in self.nodes:
            self._by_id[n.id] = n
            self._out.setdefault(n.id, [])
            self._in.setdefault(n.id, [])
        for e in self.edges:
            self._edge_ids.add(e.id)
            self._out.setdefault(e.src_id, []).append(e)
            self._in.setdefault(e.dst_id, []).append(e)
        self._indexed = True

    def node(self, node_id: str) -> GraphNode | None:
        self._ensure_index()
        return self._by_id.get(node_id)

    def has_node(self, node_id: str) -> bool:
        self._ensure_index()
        return node_id in self._by_id

    def out_edges(self, node_id: str, *, kind: EdgeKind | None = None) -> list[GraphEdge]:
        self._ensure_index()
        edges = self._out.get(node_id, [])
        return [e for e in edges if kind is None or e.kind == kind]

    def in_edges(self, node_id: str, *, kind: EdgeKind | None = None) -> list[GraphEdge]:
        self._ensure_index()
        edges = self._in.get(node_id, [])
        return [e for e in edges if kind is None or e.kind == kind]

    def neighbors(
        self,
        node_id: str,
        *,
        kind: EdgeKind | None = None,
        direction: str = "out",
    ) -> list[GraphNode]:
        self._ensure_index()
        if direction == "out":
            edges = self.out_edges(node_id, kind=kind)
            return [self._by_id[e.dst_id] for e in edges if e.dst_id in self._by_id]
        if direction == "in":
            edges = self.in_edges(node_id, kind=kind)
            return [self._by_id[e.src_id] for e in edges if e.src_id in self._by_id]
        if direction == "both":
            seen: dict[str, GraphNode] = {}
            for e in self.out_edges(node_id, kind=kind):
                if e.dst_id in self._by_id:
                    seen.setdefault(e.dst_id, self._by_id[e.dst_id])
            for e in self.in_edges(node_id, kind=kind):
                if e.src_id in self._by_id:
                    seen.setdefault(e.src_id, self._by_id[e.src_id])
            return list(seen.values())
        raise InvalidDirectionError(f"direction must be 'out' | 'in' | 'both', got {direction!r}")

    def by_kind(self, kind: NodeKind) -> list[GraphNode]:
        return [n for n in self.nodes if n.kind == kind]

    def edges_by_kind(self, kind: EdgeKind) -> list[GraphEdge]:
        return [e for e in self.edges if e.kind == kind]

    def sorted(self) -> Graph:

        def _edge_key(e: GraphEdge) -> tuple[str, str, str, str]:
            return (e.kind, e.src_id, e.dst_id, e.id)

        sorted_nodes = [n.model_copy(deep=True) for n in sorted(self.nodes, key=lambda n: n.id)]
        sorted_edges = [e.model_copy(deep=True) for e in sorted(self.edges, key=_edge_key)]
        return Graph(meta=self.meta, nodes=sorted_nodes, edges=sorted_edges)

    def merge(self, other: Graph) -> Graph:
        for n in other.nodes:
            self.add_node(n.model_copy(deep=True))
        for e in other.edges:
            self.add_edge(e.kind, e.src_id, e.dst_id, copy.deepcopy(e.attrs))
        return self

    @classmethod
    def empty(cls, meta: GraphMeta | None = None) -> Graph:
        return cls(meta=meta or GraphMeta(), nodes=[], edges=[])

    @classmethod
    def from_iterables(
        cls,
        nodes: Iterable[GraphNode],
        edges: Iterable[GraphEdge],
        *,
        meta: GraphMeta | None = None,
    ) -> Graph:
        g = cls.empty(meta)
        for n in nodes:
            g.add_node(n)
        for e in edges:
            g.add_edge(e.kind, e.src_id, e.dst_id, e.attrs)
        return g


__all__ = [
    "EdgeKind",
    "Graph",
    "GraphEdge",
    "GraphMeta",
    "GraphNode",
    "NodeKind",
    "edge_id",
]
