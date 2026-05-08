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

"""Render a standalone ``graph.html`` viewer with the JSON payload embedded.

The HTML works under ``file://`` (no server required) by exposing the
graph payload as ``window.__GRAPH__``. The ``forktex graph serve`` command
serves the same template but fetches a live payload from ``/api/graph``.
"""

from __future__ import annotations

import html as _html

from forktex.graph.models import Graph


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ForkTex graph — {scope} — {root}</title>
<style>
  :root {{
    color-scheme: light dark;
    --fg: #1a1a1a;
    --muted: #6b6b6b;
    --bg: #fafafa;
    --card: #ffffff;
    --border: #e5e5e5;
    --accent: #2a7fc1;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fg:#eaeaea;--muted:#a0a0a0;--bg:#111;--card:#1a1a1a;--border:#2a2a2a; }}
  }}
  body {{ margin:0; font:14px/1.5 system-ui,sans-serif; color:var(--fg); background:var(--bg); }}
  header {{ padding:1rem 1.5rem; border-bottom:1px solid var(--border); background:var(--card); }}
  header h1 {{ margin:0 0 .25rem; font-size:1.1rem; }}
  header .meta {{ color:var(--muted); font-size:.85rem; }}
  main {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:1rem; padding:1.5rem; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:1rem; }}
  .card h2 {{ margin:0 0 .5rem; font-size:.95rem; color:var(--accent); }}
  .kind {{ display:inline-block; padding:.05rem .4rem; border-radius:3px; background:var(--border); font-family:ui-monospace,monospace; font-size:.75rem; margin-right:.5rem; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ padding:.2rem 0; border-bottom:1px dashed var(--border); font-family:ui-monospace,monospace; font-size:.82rem; }}
  li:last-child {{ border-bottom:none; }}
  .stats {{ font-size:.85rem; color:var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>ForkTex graph · {scope} scope</h1>
  <div class="meta">root: <code>{root}</code> · generated at <code>{generated_at}</code> · schema v{schema_version}</div>
  <div class="stats" id="stats"></div>
</header>
<main id="cards"></main>
<script id="graph-data" type="application/json">{payload}</script>
<script>
  window.__GRAPH__ = JSON.parse(document.getElementById('graph-data').textContent);
  const g = window.__GRAPH__;
  const byKind = (kind) => g.nodes.filter(n => n.kind === kind);
  const edgesByKind = (kind) => g.edges.filter(e => e.kind === kind);
  const stats = document.getElementById('stats');
  stats.textContent = `${{g.nodes.length}} nodes · ${{g.edges.length}} edges`;
  const cards = document.getElementById('cards');
  const kinds = Array.from(new Set(g.nodes.map(n => n.kind))).sort();
  for (const kind of kinds) {{
    const card = document.createElement('section');
    card.className = 'card';
    const nodes = byKind(kind);
    card.innerHTML = `<h2><span class="kind">${{kind}}</span>${{nodes.length}}</h2>`;
    const ul = document.createElement('ul');
    for (const n of nodes.slice(0, 50)) {{
      const li = document.createElement('li');
      li.textContent = n.name + (n.attrs && n.attrs.rel_path ? ' — ' + n.attrs.rel_path : '');
      ul.appendChild(li);
    }}
    if (nodes.length > 50) {{
      const li = document.createElement('li');
      li.textContent = `… ${{nodes.length - 50}} more`;
      ul.appendChild(li);
    }}
    card.appendChild(ul);
    cards.appendChild(card);
  }}
  const edgeKindCard = document.createElement('section');
  edgeKindCard.className = 'card';
  edgeKindCard.innerHTML = `<h2><span class="kind">edges</span>${{g.edges.length}}</h2>`;
  const ekUl = document.createElement('ul');
  const ekCounts = {{}};
  for (const e of g.edges) ekCounts[e.kind] = (ekCounts[e.kind] || 0) + 1;
  for (const [k, v] of Object.entries(ekCounts).sort()) {{
    const li = document.createElement('li');
    li.textContent = `${{k}} — ${{v}}`;
    ekUl.appendChild(li);
  }}
  edgeKindCard.appendChild(ekUl);
  cards.appendChild(edgeKindCard);
</script>
</body>
</html>
"""


def render_html(graph: Graph, json_body: str | None = None) -> str:
    """Return a standalone HTML string for *graph*.

    If *json_body* is provided, it's embedded verbatim (the canonical
    formatted JSON written to ``graph.json``). Otherwise the graph is
    re-serialised on the fly. Both paths produce equivalent output.
    """
    if json_body is None:
        from forktex.graph.export.json_writer import render_json

        json_body = render_json(graph)
    # Defuse any "</script>" sequence that could prematurely terminate the
    # embedded data block; the JSON.parse on the client side is unaffected
    # because the unescaped sequence reads the same.
    safe_payload = json_body.replace("</", "<\\/")
    return _TEMPLATE.format(
        scope=_html.escape(graph.meta.scope),
        root=_html.escape(graph.meta.root),
        generated_at=_html.escape(graph.meta.generated_at),
        schema_version=graph.meta.schema_version,
        payload=safe_payload,
    )
