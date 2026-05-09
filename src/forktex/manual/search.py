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

"""Keyword search over the project graph (``manual@search``).

v1: case-insensitive substring match + simple TF-IDF-style ranking on
node name + attrs token frequency. No semantic search; no external
index. Builds the index on first query (lazy).

Targets ``<100ms`` for typical projects (~200 nodes). For larger
graphs the linear scan is still acceptable up to a few thousand nodes
on commodity hardware.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from forktex.graph.models import Graph, GraphNode

_TOKEN = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class SearchHit:
    node_id: str
    name: str
    kind: str
    score: float
    snippet: str


class SearchIndex:
    """In-memory keyword index over a ``Graph``.

    Construction is O(N · avg_tokens). Each query is O(N) — fast enough
    for catalog-scale projects without the complexity of an inverted
    index. Promote to inverted index if a project pushes past ~5000
    nodes.
    """

    def __init__(self, graph: Graph) -> None:
        self._graph = graph
        # Cache token bags per node + a corpus token frequency for IDF.
        self._tokens: dict[str, list[str]] = {}
        self._df: Counter[str] = Counter()
        for node in graph.nodes:
            tokens = self._tokenize_node(node)
            self._tokens[node.id] = tokens
            for tok in set(tokens):
                self._df[tok] += 1
        self._n = max(1, len(graph.nodes))

    @staticmethod
    def _tokenize_node(node: GraphNode) -> list[str]:
        parts: list[str] = [node.name, node.id, node.kind]
        for value in node.attrs.values():
            parts.append(str(value))
        joined = " ".join(parts).lower()
        return _TOKEN.findall(joined)

    def _idf(self, token: str) -> float:
        df = self._df.get(token, 0)
        if df == 0:
            return 0.0
        return math.log((self._n + 1) / (df + 1)) + 1.0

    def query(
        self,
        keyword: str,
        *,
        path_prefix: str | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        """Return ranked hits.

        ``keyword``:    case-insensitive substring matched against name +
                        attrs + id. Splits on whitespace; all sub-keywords
                        must match (AND).
        ``path_prefix``: optional filter on the node id prefix
                         (e.g. ``"file::src/forktex/manual"``).
        """
        terms = [t for t in keyword.lower().split() if t]
        if not terms:
            return []

        hits: list[SearchHit] = []
        for node in self._graph.nodes:
            if path_prefix and not node.id.startswith(path_prefix):
                continue
            tokens = self._tokens.get(node.id, [])
            if not tokens:
                continue
            joined = " ".join(tokens)
            # AND across terms — every term must appear (substring).
            if not all(term in joined for term in terms):
                continue
            score = self._score(tokens, terms, node)
            snippet = self._snippet(node, terms)
            hits.append(
                SearchHit(
                    node_id=node.id,
                    name=node.name,
                    kind=node.kind,
                    score=score,
                    snippet=snippet,
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def _score(self, tokens: list[str], terms: list[str], node: GraphNode) -> float:
        tf = Counter(tokens)
        score = 0.0
        for term in terms:
            for token, freq in tf.items():
                if term in token:
                    # exact-token match weighted higher than substring
                    weight = 2.0 if token == term else 1.0
                    score += freq * weight * self._idf(token)
        # Boost when keyword appears in the node name itself.
        name_lc = node.name.lower()
        for term in terms:
            if term in name_lc:
                score += 3.0
        return score

    @staticmethod
    def _snippet(node: GraphNode, terms: list[str]) -> str:
        joined = " · ".join(
            [node.name, node.id] + [f"{k}={v}" for k, v in sorted(node.attrs.items())]
        )
        # Truncate around the first matching term for context.
        joined_lc = joined.lower()
        for term in terms:
            idx = joined_lc.find(term)
            if idx == -1:
                continue
            start = max(0, idx - 40)
            end = min(len(joined), idx + 80)
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(joined) else ""
            return prefix + joined[start:end] + suffix
        return joined[:120]


__all__ = ["SearchHit", "SearchIndex"]
