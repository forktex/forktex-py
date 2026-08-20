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

"""Per-process Graph cache.

A single CLI invocation (or LLM agent loop) hits the query layer many
times. Rebuilding the graph each call is wasteful — instead, we build
once per project_root and reuse for the lifetime of the Python process.

Invalidation:

* Explicit: callers can invoke :func:`bust` after writes that change
  graph shape (forktex.json, Makefile).
* Automatic: :func:`session_graph` checks ``forktex.json``'s ``mtime``
  on every call. If newer than the cached graph, a fresh build replaces
  the entry.
"""

from __future__ import annotations

import threading
from pathlib import Path

from forktex.graph.build import build_graph
from forktex.graph.models import Graph
from forktex.graph.scopes import ProjectScope


_lock = threading.Lock()
_session_graphs: dict[str, tuple[Graph, float]] = {}


_GRAPH_INPUTS = ("forktex.json", "Makefile")
_SKIP_DIRS = {".git", ".venv", ".forktex", "node_modules", "__pycache__"}


def _input_mtimes(project_root: Path) -> float:
    """Return the highest mtime across files that change graph shape:
    the root ``forktex.json``/``Makefile`` plus every nested ``forktex.json``
    and ``Makefile`` reachable under the project root.
    """
    latest = 0.0
    for name in _GRAPH_INPUTS:
        candidate = project_root / name
        try:
            latest = max(latest, candidate.stat().st_mtime)
        except OSError:
            pass
    # Cheap bounded walk: rglob is acceptable here because the per-call
    # stat work is small and we already filter heavy trees.
    try:
        for child_manifest in project_root.rglob("forktex.json"):
            if any(p in _SKIP_DIRS for p in child_manifest.parts):
                continue
            try:
                latest = max(latest, child_manifest.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        pass
    return latest


def session_graph(project_root: Path, *, force_rebuild: bool = False) -> Graph:
    """Return a Graph for *project_root*, building once per process and
    reusing.

    The cache is keyed by the resolved absolute path. ``forktex.json``'s
    ``mtime`` is checked on every call; a newer manifest auto-invalidates
    the cached graph. ``force_rebuild=True`` ignores the cache entirely.
    """
    root = str(project_root.resolve())
    current_mtime = _input_mtimes(Path(root))
    with _lock:
        if not force_rebuild:
            cached = _session_graphs.get(root)
            if cached is not None:
                graph, cached_mtime = cached
                if cached_mtime >= current_mtime:
                    return graph
        graph = build_graph(ProjectScope(Path(root)))
        _session_graphs[root] = (graph, current_mtime)
        return graph


def bust(project_root: Path | None = None) -> None:
    """Drop a cached Graph (one root) or the whole cache (``None``)."""
    with _lock:
        if project_root is None:
            _session_graphs.clear()
        else:
            _session_graphs.pop(str(project_root.resolve()), None)


__all__ = ["session_graph", "bust"]
