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

"""Public types for the manual atom."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from forktex.graph.models import Graph
from forktex.models.base import ForkTexModel


class ManualScope(str, Enum):
    """Variant scope for manual generation.

    Maps 1:1 to the ``manual@<scope>`` variants declared in the FSD
    catalog (see ``src/forktex/data/fsd/standard.json``).
    """

    DEFAULT = "default"  # combines arch + graph + agents
    ARCH = "arch"  # C4 architecture (system → container → component)
    GRAPH = "graph"  # filesystem inspector + dependency tree
    AGENTS = "agents"  # AI-consumable bundle (rules, concepts, few-shots)
    SEARCH = "search"  # keyword search index over the graph

    @classmethod
    def from_str(cls, value: str | None) -> "ManualScope":
        if value is None or value == "":
            return cls.DEFAULT
        try:
            return cls(value.lower())
        except ValueError as exc:
            valid = ", ".join(s.value for s in cls)
            raise ValueError(f"unknown manual scope {value!r}; valid: {valid}") from exc


class ManualBundle(ForkTexModel):
    """The materialised manual artifact.

    Shape varies by scope:

    - ``DEFAULT``: all sub-bundles populated.
    - ``ARCH``: ``arch_html`` filled, others empty.
    - ``GRAPH``: ``graph_html`` filled.
    - ``AGENTS``: ``rules``, ``concepts``, ``few_shots`` filled.
    - ``SEARCH``: an empty bundle is returned; use ``SearchIndex`` directly.

    Serialised via ``model_dump_json()`` for AI-consumable output.
    """

    scope: ManualScope
    project_name: str
    generated_at: str  # ISO 8601 UTC

    # Human-facing renderings (HTML strings, ready to write to disk).
    arch_html: str = ""
    graph_html: str = ""

    # Agent-facing bundle.
    rules: list[str] = Field(default_factory=list)
    concepts: list[dict[str, Any]] = Field(default_factory=list)
    few_shots: list[dict[str, Any]] = Field(default_factory=list)

    # Useful per-bundle metadata.
    node_count: int = 0
    edge_count: int = 0


def generate_manual(
    graph: Graph, *, scope: ManualScope = ManualScope.DEFAULT, project_root: Any = None
) -> ManualBundle:
    """Build a ``ManualBundle`` from a project graph.

    Pure-ish: reads the graph + catalog + ``docs/AGENTS.md`` (if present)
    + ``forktex.json`` (if present). Does not touch the network. Does not
    write to disk — use ``forktex.manual.render`` to materialise the HTML
    for human scopes.

    For ``ManualScope.SEARCH`` an empty bundle is returned; use
    ``SearchIndex(graph)`` directly to query.
    """
    from datetime import datetime, timezone
    from pathlib import Path

    from forktex.manual.agents import build_agent_bundle
    from forktex.manual.render import render_arch_html, render_graph_html

    project_path = Path(project_root) if project_root is not None else None
    project_name = graph.meta.root.split("/")[-1] or "project"

    bundle = ManualBundle(
        scope=scope,
        project_name=project_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
    )

    if scope == ManualScope.SEARCH:
        return bundle

    if scope in (ManualScope.DEFAULT, ManualScope.ARCH):
        bundle.arch_html = render_arch_html(graph)

    if scope in (ManualScope.DEFAULT, ManualScope.GRAPH):
        bundle.graph_html = render_graph_html(graph)

    if scope in (ManualScope.DEFAULT, ManualScope.AGENTS):
        agent = build_agent_bundle(graph, project_path)
        bundle.rules = agent["rules"]
        bundle.concepts = agent["concepts"]
        bundle.few_shots = agent["few_shots"]

    return bundle


__all__ = ["ManualScope", "ManualBundle", "generate_manual"]
