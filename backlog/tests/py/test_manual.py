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

"""Battle tests for ``forktex.manual``."""

from __future__ import annotations

import time

from forktex.graph.models import Graph, GraphMeta, GraphNode
from forktex.manual import (
    ManualBundle,
    ManualScope,
    SearchHit,
    SearchIndex,
    generate_manual,
)


def _make_graph(nodes: list[GraphNode] | None = None) -> Graph:
    g = Graph(
        meta=GraphMeta(
            generated_at="2026-05-09T00:00:00Z",
            scope="project",
            root="/tmp/sample-project",
        ),
    )
    for node in nodes or []:
        g.add_node(node)
    return g


def _node(node_id: str, name: str, kind: str = "module", **attrs) -> GraphNode:
    return GraphNode(id=node_id, name=name, kind=kind, scope="project", attrs=attrs)


# ── ManualScope ───────────────────────────────────────────────────────────


def test_manual_scope_from_str_default_for_empty():
    assert ManualScope.from_str(None) is ManualScope.DEFAULT
    assert ManualScope.from_str("") is ManualScope.DEFAULT


def test_manual_scope_from_str_normalises_case():
    assert ManualScope.from_str("ARCH") is ManualScope.ARCH
    assert ManualScope.from_str("Search") is ManualScope.SEARCH


def test_manual_scope_from_str_rejects_unknown():
    import pytest

    with pytest.raises(ValueError):
        ManualScope.from_str("nonsense")


# ── generate_manual ───────────────────────────────────────────────────────


def test_generate_manual_search_returns_empty_bundle():
    """SEARCH scope is queried, not built — empty bundle is the contract."""
    g = _make_graph([_node("m::a", "module_a")])
    bundle = generate_manual(g, scope=ManualScope.SEARCH)
    assert isinstance(bundle, ManualBundle)
    assert bundle.scope is ManualScope.SEARCH
    assert bundle.arch_html == ""
    assert bundle.graph_html == ""
    assert bundle.rules == []
    assert bundle.concepts == []


def test_generate_manual_graph_scope_renders_html():
    g = _make_graph(
        [
            _node("m::api", "api", kind="package"),
            _node("m::api.handler", "handler", rel_path="api/handler.py"),
        ]
    )
    bundle = generate_manual(g, scope=ManualScope.GRAPH)
    assert bundle.scope is ManualScope.GRAPH
    assert bundle.graph_html  # non-empty
    assert "api" in bundle.graph_html
    assert "handler" in bundle.graph_html
    assert bundle.arch_html == ""  # only graph scope was requested


def test_generate_manual_default_renders_arch_and_graph_and_agents(tmp_path):
    g = _make_graph(
        [
            _node("m::api", "api", kind="package"),
            _node("m::api.h", "h", rel_path="api/h.py"),
        ]
    )
    bundle = generate_manual(g, scope=ManualScope.DEFAULT, project_root=tmp_path)
    assert bundle.scope is ManualScope.DEFAULT
    assert bundle.graph_html
    # arch_html depends on the c4 writer; on a tiny synthetic graph it
    # should at least be non-empty.
    assert bundle.arch_html
    # agents bundle: concepts pulled from the live FSD catalog (>= 21 atoms)
    assert any(c["kind"] == "fsd-atom" for c in bundle.concepts)


def test_generate_manual_node_count_matches_graph():
    g = _make_graph([_node(f"m::{i}", f"node_{i}") for i in range(5)])
    bundle = generate_manual(g, scope=ManualScope.GRAPH)
    assert bundle.node_count == 5


# ── SearchIndex ───────────────────────────────────────────────────────────


def test_search_index_substring_match():
    g = _make_graph(
        [
            _node("m::auth", "auth_handler", purpose="login flow"),
            _node("m::cache", "cache_layer", purpose="redis wrapper"),
            _node("m::auth.session", "session_store", purpose="auth session"),
        ]
    )
    idx = SearchIndex(g)
    hits = idx.query("auth")
    assert hits, "expected hits for keyword 'auth'"
    assert all(isinstance(h, SearchHit) for h in hits)
    # Both auth-named nodes should appear; cache should not.
    names = [h.name for h in hits]
    assert "auth_handler" in names
    assert "session_store" in names
    assert "cache_layer" not in names


def test_search_index_ranks_name_match_above_attr_match():
    g = _make_graph(
        [
            _node("m::a", "alpha", purpose="contains the word target"),
            _node("m::b", "target", purpose="some other text"),
        ]
    )
    idx = SearchIndex(g)
    hits = idx.query("target")
    assert hits[0].name == "target"
    assert hits[1].name == "alpha"


def test_search_index_path_prefix_filter():
    g = _make_graph(
        [
            _node("file::src/a.py", "a"),
            _node("file::tests/a.py", "a_test"),
        ]
    )
    idx = SearchIndex(g)
    hits = idx.query("a", path_prefix="file::src/")
    assert len(hits) == 1
    assert hits[0].node_id == "file::src/a.py"


def test_search_index_multi_term_and():
    g = _make_graph(
        [
            _node("m::1", "auth_login_handler"),
            _node("m::2", "auth_session_store"),
            _node("m::3", "cache_login_helper"),
        ]
    )
    idx = SearchIndex(g)
    hits = idx.query("auth login")
    names = [h.name for h in hits]
    assert "auth_login_handler" in names
    assert "auth_session_store" not in names
    assert "cache_login_helper" not in names


def test_search_index_empty_keyword_returns_empty():
    g = _make_graph([_node("m::a", "a")])
    idx = SearchIndex(g)
    assert idx.query("") == []
    assert idx.query("   ") == []


def test_search_index_query_is_fast():
    """For a 200-node synthetic project the query should comfortably stay
    under 100 ms on commodity hardware."""
    nodes = [
        _node(f"m::{i}", f"module_{i}", purpose=f"file_{i % 10}.py") for i in range(200)
    ]
    g = _make_graph(nodes)
    idx = SearchIndex(g)
    start = time.perf_counter()
    hits = idx.query("module")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert hits  # sanity: query returned results
    # Generous bound — naive scan is fast enough for catalog-scale projects.
    assert elapsed_ms < 250, f"query took {elapsed_ms:.1f}ms (>250ms)"
