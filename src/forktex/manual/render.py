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

"""HTML rendering for human-facing manual scopes."""

from __future__ import annotations

from html import escape

from forktex.graph.models import Graph


def render_arch_html(graph: Graph) -> str:
    """C4 architecture page — wraps ``forktex.graph.export.c4_html_writer``."""
    from forktex.graph.export.c4_html_writer import render_c4_html

    return render_c4_html(graph)


def render_graph_html(graph: Graph) -> str:
    """Filesystem inspector + dependency tree, single-page HTML.

    Groups nodes by ``kind`` and renders each group as a collapsible
    section. Edges are listed under their source node. No external
    assets — pure self-contained HTML for offline reading.
    """
    by_kind: dict[str, list] = {}
    for node in graph.nodes:
        by_kind.setdefault(node.kind, []).append(node)

    # Sort each kind's nodes by name for stable output.
    for kind in by_kind:
        by_kind[kind].sort(key=lambda n: n.name)

    # Outgoing edges per node id.
    out_edges: dict[str, list] = {}
    for edge in graph.edges:
        out_edges.setdefault(edge.src_id, []).append(edge)

    sections: list[str] = []
    for kind in sorted(by_kind):
        nodes = by_kind[kind]
        rows: list[str] = []
        for node in nodes:
            edges = out_edges.get(node.id, [])
            edge_html = ""
            if edges:
                items = "".join(
                    f"<li><code>{escape(e.kind)}</code> → "
                    f"<code>{escape(e.dst_id)}</code></li>"
                    for e in edges[:50]
                )
                more = ""
                if len(edges) > 50:
                    more = f"<li><em>… and {len(edges) - 50} more</em></li>"
                edge_html = f"<ul class='edges'>{items}{more}</ul>"
            attrs_html = ""
            if node.attrs:
                attrs_html = (
                    "<dl class='attrs'>"
                    + "".join(
                        f"<dt>{escape(str(k))}</dt><dd>{escape(str(v))}</dd>"
                        for k, v in sorted(node.attrs.items())
                    )
                    + "</dl>"
                )
            rows.append(
                f"<details><summary><strong>{escape(node.name)}</strong> "
                f"<code class='id'>{escape(node.id)}</code></summary>"
                f"{attrs_html}{edge_html}</details>"
            )
        sections.append(
            f"<section><h2>{escape(kind)} <span class='count'>"
            f"({len(nodes)})</span></h2>{''.join(rows)}</section>"
        )

    return _GRAPH_HTML_TEMPLATE.format(
        title=escape(graph.meta.root or "project"),
        scope=escape(graph.meta.scope),
        generated_at=escape(graph.meta.generated_at),
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        body="".join(sections),
    )


_GRAPH_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>forktex manual @ graph — {title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
header {{ border-bottom: 2px solid #333; padding-bottom: 0.5rem; margin-bottom: 1rem; }}
header h1 {{ margin: 0 0 0.25rem; }}
header .meta {{ color: #666; font-size: 0.9rem; }}
section {{ margin: 1.5rem 0; }}
section h2 {{ border-bottom: 1px solid #ddd; padding-bottom: 0.3rem;
              margin-bottom: 0.5rem; }}
section h2 .count {{ color: #888; font-weight: normal; font-size: 0.85em; }}
details {{ margin: 0.4rem 0 0.4rem 0.5rem; }}
details summary {{ cursor: pointer; padding: 0.2rem 0; }}
code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
       background: #f3f3f3; padding: 0 0.25rem; border-radius: 3px; }}
code.id {{ background: transparent; color: #888; font-size: 0.85em; }}
ul.edges {{ list-style: none; padding-left: 1.5rem; margin: 0.3rem 0; }}
ul.edges li {{ padding: 0.1rem 0; font-size: 0.92em; }}
dl.attrs {{ margin: 0.3rem 0 0.3rem 1.5rem; display: grid;
            grid-template-columns: max-content 1fr; gap: 0.2rem 0.6rem;
            font-size: 0.92em; }}
dl.attrs dt {{ color: #666; }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">scope: <code>{scope}</code> · generated: <code>{generated_at}</code>
       · {node_count} nodes · {edge_count} edges</div>
</header>
<main>
{body}
</main>
</body>
</html>
"""


__all__ = ["render_arch_html", "render_graph_html"]
