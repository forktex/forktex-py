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

"""AI-consumable bundle for ``manual@agents``.

Builds a JSON-serialisable dict with three sections:

- ``rules``: project conventions (one bullet per rule). Sources:
  AGENTS.md (top-level "Preferences" / "Rules" / "Don'ts" sections),
  forktex.json (any ``fsd.atoms[*].description`` overrides).
- ``concepts``: structured entries about the FSD catalog + the
  project's most-connected modules. Each concept: ``{name, kind,
  summary}``.
- ``few_shots``: representative tasks pulled from AGENTS.md's "Local
  Operator Loop" section + a small fixed set of common operations.

v1: deterministic, no LLM calls. v1.x: optionally enrich via
``forktex_intelligence`` once that integration is wired.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forktex.graph.models import Graph


def build_agent_bundle(graph: Graph, project_root: Path | None) -> dict[str, list[Any]]:
    rules = _extract_rules(project_root)
    concepts = _extract_concepts(graph, project_root)
    few_shots = _extract_few_shots(project_root)
    return {
        "rules": rules,
        "concepts": concepts,
        "few_shots": few_shots,
    }


def _extract_rules(project_root: Path | None) -> list[str]:
    rules: list[str] = []
    if project_root is None:
        return rules
    agents_md = project_root / "AGENTS.md"
    if not agents_md.is_file():
        agents_md = project_root / "docs" / "AGENTS.md"
    if not agents_md.is_file():
        return rules
    try:
        text = agents_md.read_text(encoding="utf-8")
    except OSError:
        return rules

    # Pull bullet lines from sections that read like rule lists.
    capture = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()
        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            capture = any(
                kw in heading
                for kw in (
                    "principle",
                    "preference",
                    "rule",
                    "don't",
                    "do not",
                    "first principle",
                )
            )
            continue
        if not capture:
            continue
        if stripped.startswith(("- ", "* ")):
            rules.append(stripped[2:].strip())
    return rules[:50]


def _extract_concepts(graph: Graph, project_root: Path | None) -> list[dict[str, Any]]:
    concepts: list[dict[str, Any]] = []

    # 1) FSD catalog — atoms + their descriptions.
    try:
        from forktex.fsd.loader import load_standard

        standard = load_standard()
    except Exception:  # pragma: no cover
        standard = None
    if standard is not None:
        for atom in standard.atoms:
            concepts.append(
                {
                    "name": atom.id,
                    "kind": "fsd-atom",
                    "summary": atom.description or "",
                }
            )

    # 2) Most-connected modules from the graph (top 15 by degree).
    in_deg: dict[str, int] = {}
    out_deg: dict[str, int] = {}
    for edge in graph.edges:
        out_deg[edge.src_id] = out_deg.get(edge.src_id, 0) + 1
        in_deg[edge.dst_id] = in_deg.get(edge.dst_id, 0) + 1
    by_id = {n.id: n for n in graph.nodes}
    ranked = sorted(
        graph.nodes,
        key=lambda n: out_deg.get(n.id, 0) + in_deg.get(n.id, 0),
        reverse=True,
    )
    for node in ranked[:15]:
        concepts.append(
            {
                "name": node.name,
                "kind": f"node:{node.kind}",
                "summary": (
                    f"degree {out_deg.get(node.id, 0) + in_deg.get(node.id, 0)} "
                    f"(in={in_deg.get(node.id, 0)}, out={out_deg.get(node.id, 0)})"
                ),
            }
        )

    # 3) Project name as a concept anchor.
    if project_root is not None:
        concepts.insert(
            0,
            {
                "name": project_root.name,
                "kind": "project",
                "summary": f"Root: {project_root}",
            },
        )

    _ = by_id  # reserved for future use
    return concepts


def _extract_few_shots(project_root: Path | None) -> list[dict[str, Any]]:
    """Representative tasks. Static set + AGENTS.md "Useful Make targets"."""
    few_shots: list[dict[str, Any]] = [
        {
            "task": "Run the project quality gate",
            "command": "make gate",
            "expected": "format-check + lint + license + security + test + build all green",
        },
        {
            "task": "Battle-test the published surface",
            "command": "make acceptance",
            "expected": "wheel installs into a clean venv; CLI verbs all respond",
        },
        {
            "task": "Audit FSD compliance",
            "command": "forktex fsd check",
            "expected": "per-atom PASS/FAIL/N/A report and a maturity level",
        },
        {
            "task": "Build the architecture graph",
            "command": "forktex graph build",
            "expected": "graph.json + graph.dsl + graph.html under .forktex/",
        },
        {
            "task": "Search the project graph",
            "command": "forktex manual search <keyword>",
            "expected": "ranked node hits matching the keyword",
        },
    ]

    if project_root is None:
        return few_shots
    agents_md = project_root / "AGENTS.md"
    if not agents_md.is_file():
        agents_md = project_root / "docs" / "AGENTS.md"
    if not agents_md.is_file():
        return few_shots
    try:
        text = agents_md.read_text(encoding="utf-8")
    except OSError:
        return few_shots

    in_targets = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            in_targets = "make target" in heading or "operator loop" in heading
            continue
        if not in_targets:
            continue
        stripped = line.lstrip()
        if stripped.startswith("make ") or stripped.startswith("forktex "):
            few_shots.append(
                {
                    "task": f"From AGENTS.md: {stripped}",
                    "command": stripped,
                    "expected": "(see AGENTS.md for context)",
                }
            )
    return few_shots[:20]


__all__ = ["build_agent_bundle"]
