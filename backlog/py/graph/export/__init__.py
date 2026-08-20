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

"""Export the source-of-truth graph to stable filenames.

The three export formats — JSON, DSL, HTML — are all rendered from the
same in-memory :class:`Graph` so they share one ``meta.generated_at``
timestamp. Filenames are stable (no timestamp suffix); each export
overwrites the previous one. The JSON body is the canonical artifact;
DSL and HTML are projections.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forktex.graph.export.dsl_writer import render_dsl
from forktex.graph.export.html_writer import render_html
from forktex.graph.export.json_writer import render_json
from forktex.graph.io_proxy import tracked_write
from forktex.graph.models import Graph


GRAPH_JSON = "graph.json"
GRAPH_DSL = "graph.dsl"
GRAPH_HTML = "graph.html"


@dataclass(frozen=True)
class ExportPaths:
    json_path: Path
    dsl_path: Path
    html_path: Path


def export_graph(graph: Graph, out_dir: Path) -> ExportPaths:
    """Write ``graph.{json,dsl,html}`` into *out_dir* atomically.

    ``out_dir`` should be ``<root>/.forktex/`` for project scope or
    ``~/.forktex/`` for OS scope. Writes route through
    :func:`forktex.graph.io_proxy.tracked_write` so the structure spec is
    enforced and the registry is updated.
    """

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    json_body = render_json(graph)
    dsl_body = render_dsl(graph)
    html_body = render_html(graph, json_body)

    json_path = tracked_write(
        out_dir / GRAPH_JSON,
        json_body,
        kind="graph_export",
        writer="forktex.graph.export.json_writer",
    )
    dsl_path = tracked_write(
        out_dir / GRAPH_DSL,
        dsl_body,
        kind="graph_export",
        writer="forktex.graph.export.dsl_writer",
    )
    html_path = tracked_write(
        out_dir / GRAPH_HTML,
        html_body,
        kind="graph_export",
        writer="forktex.graph.export.html_writer",
    )
    return ExportPaths(json_path=json_path, dsl_path=dsl_path, html_path=html_path)


__all__ = ["ExportPaths", "export_graph", "render_dsl", "render_html", "render_json"]
