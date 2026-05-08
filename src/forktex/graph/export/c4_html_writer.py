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

"""Render a per-platform nested C4 HTML view from the graph.

The C4 viewer is a self-contained drill-down page: Workspace → Systems →
Containers → Components, with breadcrumbs and visible nesting. Mirrors
the UX of the legacy ``forktex arch`` HTML reports without the legacy
template plumbing.

The ``Workspace`` payload is embedded as ``window.__C4__`` so the page
works under ``file://`` (no server needed). ``forktex serve`` exposes
the same template at ``/c4`` with a freshly built workspace per request.
"""

from __future__ import annotations

import html as _html
import json

from forktex.architecture.models import Workspace
from forktex.graph.models import Graph
from forktex.graph.views.c4 import graph_to_workspace


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ForkTex C4 — {workspace_name} — {scope}</title>
<style>
  :root {{
    color-scheme: light dark;
    --fg:#1a1a1a; --muted:#6b6b6b; --bg:#fafafa;
    --card:#fff; --border:#e5e5e5;
    --system:#0b3c5d; --container:#2a7fc1;
    --component:#4a90d9; --persist:#1a6d3a;
    --observability:#7d4cb8; --link:#0b6dc7;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fg:#eaeaea;--muted:#a0a0a0;--bg:#111;--card:#1a1a1a;--border:#2a2a2a;--link:#5aa9f0; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:14px/1.5 system-ui,sans-serif; color:var(--fg); background:var(--bg); }}
  header {{ padding:1rem 1.25rem; border-bottom:1px solid var(--border); background:var(--card); position:sticky; top:0; z-index:5; }}
  header h1 {{ margin:0 0 .25rem; font-size:1.05rem; }}
  header .meta {{ color:var(--muted); font-size:.78rem; }}
  nav.crumbs {{ display:flex; gap:.4rem; flex-wrap:wrap; align-items:center; padding:.5rem 1.25rem; border-bottom:1px solid var(--border); background:var(--bg); }}
  nav.crumbs button {{ all:unset; cursor:pointer; color:var(--link); font:inherit; }}
  nav.crumbs button:hover {{ text-decoration:underline; }}
  nav.crumbs .sep {{ color:var(--muted); }}
  main {{ padding:1.25rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:.75rem; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:.85rem 1rem; cursor:pointer; transition:transform .08s, box-shadow .08s; }}
  .card:hover {{ transform:translateY(-1px); box-shadow:0 2px 8px rgba(0,0,0,.08); }}
  .card.system  {{ border-left:4px solid var(--system); }}
  .card.compute {{ border-left:4px solid var(--container); }}
  .card.persist {{ border-left:4px solid var(--persist); }}
  .card.observability {{ border-left:4px solid var(--observability); }}
  .card.component {{ border-left:4px solid var(--component); cursor:default; }}
  .card.component:hover {{ transform:none; box-shadow:none; }}
  .card h3 {{ margin:0 0 .25rem; font-size:.95rem; }}
  .card .desc {{ color:var(--muted); font-size:.82rem; margin-bottom:.45rem; }}
  .card .meta-row {{ display:flex; gap:.4rem; flex-wrap:wrap; font-size:.72rem; color:var(--muted); }}
  .tag {{ background:var(--bg); border:1px solid var(--border); border-radius:3px; padding:.05rem .35rem; font-family:ui-monospace,monospace; }}
  .ports-table {{ width:100%; border-collapse:collapse; margin-top:1rem; font-size:.85rem; }}
  .ports-table th, .ports-table td {{ text-align:left; padding:.35rem .5rem; border-bottom:1px solid var(--border); }}
  .ports-table th {{ color:var(--muted); font-weight:600; }}
  details summary {{ cursor:pointer; padding:.4rem 0; user-select:none; }}
  details summary::marker {{ color:var(--muted); }}
  .empty {{ color:var(--muted); font-style:italic; padding:.5rem 0; }}
  .panel {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:1rem 1.25rem; margin-bottom:1rem; }}
  .panel h2 {{ margin:0 0 .35rem; font-size:1rem; }}
  .panel .desc {{ color:var(--muted); font-size:.85rem; }}
  .stats {{ display:flex; gap:1rem; margin-top:.75rem; font-size:.78rem; color:var(--muted); }}
  code {{ font-family:ui-monospace,monospace; font-size:.78rem; }}
  .kind {{ display:inline-block; padding:.05rem .4rem; border-radius:3px; font-family:ui-monospace,monospace; font-size:.72rem; background:var(--bg); border:1px solid var(--border); margin-right:.4rem; }}
</style>
</head>
<body>
<header>
  <h1 id="title">ForkTex C4</h1>
  <div class="meta" id="header-meta"></div>
</header>
<nav class="crumbs" id="crumbs"></nav>
<main id="view"></main>
<script id="c4-data" type="application/json">{payload}</script>
<script>
{js}
</script>
</body>
</html>
"""


# Inline JS is kept readable (~140 LOC). It owns the drill-down state and
# rerenders the main panel when the user navigates. No framework — plain
# DOM + a tiny path-based state.
_JS = r"""
'use strict';
const W = JSON.parse(document.getElementById('c4-data').textContent);
window.__C4__ = W;

const SCOPE = document.body.dataset.scope || (W && W._scope) || 'project';
const ROOT  = (W && W._root) || '';
const GENERATED = (W && W._generated_at) || '';

document.getElementById('title').textContent =
  `ForkTex C4 · ${W.name || 'workspace'}`;
document.getElementById('header-meta').innerHTML =
  `scope: <code>${escapeHtml(SCOPE)}</code> · root: <code>${escapeHtml(ROOT)}</code> · generated at <code>${escapeHtml(GENERATED)}</code>`;

const view = document.getElementById('view');
const crumbsEl = document.getElementById('crumbs');

// Path through the model: [] = workspace, [sysId] = system,
// [sysId, ctrId] = container, [sysId, ctrId, compId] = component.
let path = [];

function escapeHtml(s) {
  if (s === undefined || s === null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function findSystem(id) {
  return (W.systems || []).find(s => s.id === id);
}
function findContainer(sys, id) {
  return (sys.containers || []).find(c => c.id === id);
}
function findComponent(ctr, id) {
  return (ctr.components || []).find(c => c.id === id);
}

function navigate(newPath) {
  path = newPath;
  render();
  history.replaceState(null, '', '#' + path.map(encodeURIComponent).join('/'));
}

window.addEventListener('hashchange', () => {
  const fromHash = location.hash.replace(/^#/, '');
  path = fromHash ? fromHash.split('/').map(decodeURIComponent) : [];
  render();
});

function renderCrumbs() {
  const crumbs = [{label: W.name || 'workspace', path: []}];
  if (path[0]) {
    const s = findSystem(path[0]);
    if (s) crumbs.push({label: s.name, path: [s.id]});
  }
  if (path[1]) {
    const s = findSystem(path[0]);
    const c = s && findContainer(s, path[1]);
    if (c) crumbs.push({label: c.name, path: [path[0], c.id]});
  }
  if (path[2]) {
    const s = findSystem(path[0]);
    const c = s && findContainer(s, path[1]);
    const cmp = c && findComponent(c, path[2]);
    if (cmp) crumbs.push({label: cmp.name, path: [path[0], path[1], cmp.id]});
  }
  crumbsEl.innerHTML = crumbs.map((cb, i) => {
    const sep = i ? '<span class="sep">›</span>' : '';
    return `${sep}<button data-path="${cb.path.join('/')}">${escapeHtml(cb.label)}</button>`;
  }).join(' ');
  crumbsEl.querySelectorAll('button').forEach(btn => {
    btn.addEventListener('click', () => {
      const p = btn.dataset.path;
      navigate(p ? p.split('/') : []);
    });
  });
}

function renderWorkspace() {
  const systems = W.systems || [];
  const all_ports = W.all_ports || [];
  const sysCards = systems.map(s => {
    const containerCount = (s.containers || []).length;
    const portCount = (s.containers || []).reduce(
      (n, c) => n + ((c.ports || []).length), 0,
    );
    return `
      <div class="card system" data-sys="${escapeHtml(s.id)}">
        <h3>${escapeHtml(s.name)}</h3>
        <div class="desc">${escapeHtml(s.description || '')}</div>
        <div class="meta-row">
          <span class="tag">${containerCount} container${containerCount === 1 ? '' : 's'}</span>
          ${portCount ? `<span class="tag">${portCount} port${portCount === 1 ? '' : 's'}</span>` : ''}
          ${s.fsd_level ? `<span class="tag">${escapeHtml(s.fsd_level)}</span>` : ''}
        </div>
      </div>
    `;
  }).join('');

  const portsHtml = all_ports.length ? `
    <div class="panel">
      <h2>All ports</h2>
      <table class="ports-table">
        <thead><tr><th>Host</th><th>Container</th><th>System</th><th>Container</th><th>Type</th></tr></thead>
        <tbody>
          ${all_ports.map(p => `
            <tr>
              <td><code>${escapeHtml(String(p.host_port))}</code></td>
              <td><code>${escapeHtml(String(p.container_port))}</code></td>
              <td>${escapeHtml(p.system)}</td>
              <td>${escapeHtml(p.container)}</td>
              <td><span class="tag">${escapeHtml(p.type)}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>` : '';

  view.innerHTML = `
    <div class="panel">
      <h2>${escapeHtml(W.name || 'workspace')}</h2>
      <div class="desc">${escapeHtml(W.description || '')}</div>
      <div class="stats">
        <span><span class="kind">systems</span>${systems.length}</span>
        <span><span class="kind">ports</span>${all_ports.length}</span>
      </div>
    </div>
    ${systems.length ? `<div class="grid">${sysCards}</div>` : '<div class="empty">no systems in this scope</div>'}
    ${portsHtml}
  `;
  view.querySelectorAll('.card.system').forEach(card => {
    card.addEventListener('click', () => navigate([card.dataset.sys]));
  });
}

function renderSystem(sys) {
  const containers = sys.containers || [];
  const cards = containers.map(c => {
    const klass = c.service_type === 'persistence' ? 'persist'
               : c.service_type === 'observability' ? 'observability'
               : 'compute';
    const ports = (c.ports || []).map(p =>
      `<span class="tag">:${p.host}→${p.container}</span>`).join(' ');
    const tech = (c.technology || []).map(t => escapeHtml(t.name)).join(', ');
    return `
      <div class="card ${klass}" data-ctr="${escapeHtml(c.id)}">
        <h3>${escapeHtml(c.name)}</h3>
        <div class="desc">${escapeHtml(c.description || '')}</div>
        <div class="meta-row">
          <span class="tag">${escapeHtml(c.service_type || 'compute')}</span>
          ${tech ? `<span class="tag">${tech}</span>` : ''}
          <span class="tag">${(c.components || []).length} component${(c.components || []).length === 1 ? '' : 's'}</span>
          ${ports}
        </div>
      </div>
    `;
  }).join('');
  view.innerHTML = `
    <div class="panel">
      <h2>${escapeHtml(sys.name)}</h2>
      <div class="desc">${escapeHtml(sys.description || '')}</div>
      <div class="stats">
        <span><span class="kind">containers</span>${containers.length}</span>
        <span><span class="kind">domains</span>${(sys.domains || []).length}</span>
        ${sys.fsd_level ? `<span><span class="kind">FSD</span>${escapeHtml(sys.fsd_level)}</span>` : ''}
      </div>
    </div>
    ${containers.length ? `<div class="grid">${cards}</div>` : '<div class="empty">no containers</div>'}
  `;
  view.querySelectorAll('.card[data-ctr]').forEach(card => {
    card.addEventListener('click', () =>
      navigate([sys.id, card.dataset.ctr]));
  });
}

function renderContainer(sys, ctr) {
  const components = ctr.components || [];
  const ports = ctr.ports || [];
  const tech = (ctr.technology || []).map(t =>
    `${escapeHtml(t.name)}${t.version ? ' ' + escapeHtml(t.version) : ''}`).join(', ');
  const cards = components.map(c => `
    <div class="card component" data-cmp="${escapeHtml(c.id)}">
      <h3>${escapeHtml(c.name)}</h3>
      <div class="desc">${escapeHtml(c.description || '')}</div>
      ${(c.files || []).length ? `<div class="meta-row">${(c.files || []).map(f => `<span class="tag">${escapeHtml(f)}</span>`).join('')}</div>` : ''}
    </div>
  `).join('');
  const portsTable = ports.length ? `
    <div class="panel">
      <h2>Ports</h2>
      <table class="ports-table">
        <thead><tr><th>Host</th><th>Container</th><th>Protocol</th></tr></thead>
        <tbody>${ports.map(p => `
          <tr>
            <td><code>${escapeHtml(String(p.host))}</code></td>
            <td><code>${escapeHtml(String(p.container))}</code></td>
            <td><span class="tag">${escapeHtml(p.protocol || 'TCP')}</span></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>` : '';
  view.innerHTML = `
    <div class="panel">
      <h2>${escapeHtml(ctr.name)}</h2>
      <div class="desc">${escapeHtml(ctr.description || '')}</div>
      <div class="stats">
        <span><span class="kind">type</span>${escapeHtml(ctr.service_type || 'compute')}</span>
        ${tech ? `<span><span class="kind">tech</span>${tech}</span>` : ''}
        ${ctr.image ? `<span><span class="kind">image</span><code>${escapeHtml(ctr.image)}</code></span>` : ''}
        <span><span class="kind">components</span>${components.length}</span>
      </div>
    </div>
    ${portsTable}
    ${components.length ? `<div class="grid">${cards}</div>` : '<div class="empty">no components</div>'}
  `;
}

function renderComponent(sys, ctr, cmp) {
  view.innerHTML = `
    <div class="panel">
      <h2>${escapeHtml(cmp.name)}</h2>
      <div class="desc">${escapeHtml(cmp.description || '')}</div>
      ${cmp.tech_summary ? `<div class="stats"><span><span class="kind">tech</span>${escapeHtml(cmp.tech_summary)}</span></div>` : ''}
    </div>
    ${(cmp.files || []).length ? `
      <div class="panel">
        <h2>Files</h2>
        <ul style="margin:0;padding:0;list-style:none;font-family:ui-monospace,monospace;font-size:.85rem;">
          ${cmp.files.map(f => `<li style="padding:.2rem 0;border-bottom:1px dashed var(--border);">${escapeHtml(f)}</li>`).join('')}
        </ul>
      </div>` : ''}
  `;
}

function render() {
  renderCrumbs();
  if (path.length === 0) return renderWorkspace();
  const sys = findSystem(path[0]);
  if (!sys) { path = []; return renderWorkspace(); }
  if (path.length === 1) return renderSystem(sys);
  const ctr = findContainer(sys, path[1]);
  if (!ctr) { path = [path[0]]; return renderSystem(sys); }
  if (path.length === 2) return renderContainer(sys, ctr);
  const cmp = findComponent(ctr, path[2]);
  if (!cmp) { path = path.slice(0, 2); return renderContainer(sys, ctr); }
  renderComponent(sys, ctr, cmp);
}

// Bootstrap from URL hash if present.
const initial = location.hash.replace(/^#/, '');
path = initial ? initial.split('/').map(decodeURIComponent) : [];
render();
"""


def _augment(workspace_dict: dict, graph: Graph) -> dict:
    """Add scope/root/generated_at metadata for the JS to display."""
    workspace_dict["_scope"] = graph.meta.scope
    workspace_dict["_root"] = graph.meta.root
    workspace_dict["_generated_at"] = graph.meta.generated_at
    return workspace_dict


def render_c4_html(graph: Graph) -> str:
    """Return a standalone, drill-down-capable HTML C4 view."""
    workspace: Workspace = graph_to_workspace(graph)
    payload = _augment(workspace.model_dump(mode="json"), graph)
    payload_json = json.dumps(payload, default=str).replace("</", "<\\/")
    return _PAGE.format(
        workspace_name=_html.escape(workspace.name),
        scope=_html.escape(graph.meta.scope),
        payload=payload_json,
        js=_JS,
    )
