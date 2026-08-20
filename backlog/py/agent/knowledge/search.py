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

"""Tokenised, ranked keyword search over the query core.

``FractalQuery.search_nodes`` matches the *whole* query string as a substring —
fine for a single term, useless for a natural-language ask ("real database tests
with no mocks"). This helper splits the query into tokens, searches each, and
ranks nodes by how many distinct query tokens they match. Zero-infra (no Qdrant);
semantic RAG via ``KnowledgeIndex.assemble`` is the heavier, optional upgrade.
"""

from __future__ import annotations

import re

from forktex_core.fractal import FractalQuery
from forktex_core.fractal.query import NodeSummary

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "the a an of to in for and or with how do does is are on at by be it this that "
    "what when where which use using via from into your our".split()
)


def ranked_search(
    query: FractalQuery,
    namespace: str,
    text: str,
    *,
    kind: str | None = None,
    limit: int = 10,
) -> list[NodeSummary]:
    """Return nodes ranked by how many distinct query tokens they match.

    Falls back to a raw whole-string search when the query has no usable tokens.
    Raises ``NamespaceNotFound`` (from the query core) for an unknown namespace.
    """
    # ``>= 2`` keeps high-signal tech tokens (uv, ci, go, ai, db, ml); 2-char
    # noise (of/to/in/is/on/…) is already filtered by the stopword set.
    tokens = [
        t for t in _TOKEN.findall(text.lower()) if len(t) >= 2 and t not in _STOPWORDS
    ]
    if not tokens:
        return query.search_nodes(namespace, text, kind=kind, limit=limit).nodes

    scores: dict[str, int] = {}
    summaries: dict[str, NodeSummary] = {}
    for token in dict.fromkeys(tokens):  # unique, order-preserving
        for node in query.search_nodes(namespace, token, kind=kind, limit=200).nodes:
            scores[node.id] = scores.get(node.id, 0) + 1
            summaries[node.id] = node

    ranked = sorted(summaries.values(), key=lambda n: (-scores[n.id], n.id))
    return ranked[:limit]


__all__ = ["ranked_search"]
