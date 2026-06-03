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

"""Rollup — compact a resolved subtree into its parent summary (runtime maintenance).

The fractal-of-fractals analogue of context compaction: when a subtree has
*resolved* (the decision was made, the lesson captured), collapse its detail
into the parent's curated ``summary`` and demote each child to
``status="rolled-up"`` so retrieval prefers the compact summary over re-loading
each leaf. Bounds the working set as the project doc-space accumulates.

Policy (when to roll up, what to keep) is a *runtime* concern — this helper
lives in forktex-py, over the core ``Workspace``/``Patch``/``io`` primitives.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from forktex_core.fractal import (
    Node,
    Patch,
    load_workspace,
    serialize_node,
    serialize_patch,
)

from forktex.graph.io_proxy import tracked_write

ROLLUP_PATCH_KIND = "rollup"
STATUS_ROLLED_UP = "rolled-up"

#: Tracked-write writer identity — recorded in the ``.forktex/registry`` so the
#: parent + each demoted child traces back to this rollup invocation.
_WRITER = "forktex.agent.knowledge.rollup"


def rollup(
    doc_space: str | Path,
    parent_id: str,
    *,
    summary: str | None = None,
    child_ids: Sequence[str] | None = None,
    agent: str | None = None,
) -> Node:
    """Compact ``parent_id``'s children into its summary; demote them.

    Loads ``doc_space``, gathers the parent's children (or uses the explicit
    ``child_ids``), composes a ``summary`` from their summaries when none is
    given, refreshes the parent + stamps each child ``status='rolled-up'``, and
    writes a provenance ``Patch``. Returns the refreshed parent.

    Children are *derived* from the typed graph: nodes whose ``edges['parent']``
    contains ``parent_id``. An empty subtree raises ``ValueError`` (nothing to
    compact). A child without a ``summary`` falls back to its title.
    """
    space = Path(doc_space)
    nodes_dir = space / "nodes"
    patches_dir = space / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)

    ws = load_workspace(space)
    parent = ws.nodes.get(parent_id)
    if parent is None:
        raise KeyError(f"parent {parent_id!r} not found in {space}")

    if child_ids is None:
        children = [
            n for n in ws.nodes.values() if parent_id in n.edges.get("parent", [])
        ]
    else:
        children = [ws.nodes[cid] for cid in child_ids if cid in ws.nodes]

    if not children:
        raise ValueError(f"no children to rollup under {parent_id!r}")

    today = date.today().isoformat()
    composed = summary or _compose_summary(children)

    # Refresh the parent: new compact summary + freshness + provenance link.
    # Atomic write — a concurrent reader never sees a half-rewritten parent.
    parent.summary = composed
    parent.updated_at = today
    parent.provenance_patch_id = f"patch.rollup.{parent_id}"
    tracked_write(
        nodes_dir / f"{parent_id}.md",
        serialize_node(parent),
        kind="knowledge_node",
        writer=_WRITER,
    )

    # Demote each child: retrieval ranks summaries; ``rolled-up`` is the signal
    # to consumers that the detail has been folded upward. Per-file atomicity
    # only — a multi-child rollup can be partially observed mid-flight (parent
    # refreshed, some children demoted, others not). For v1 we accept that;
    # readers ignore rolled-up children regardless of when the demotion lands.
    for child in children:
        child.status = STATUS_ROLLED_UP
        child.updated_at = today
        tracked_write(
            nodes_dir / f"{child.id}.md",
            serialize_node(child),
            kind="knowledge_node",
            writer=_WRITER,
        )

    patch = Patch(
        id=f"patch.rollup.{parent_id}",
        kind=ROLLUP_PATCH_KIND,
        title=f"rollup {parent_id} ({len(children)} children)",
        agent=agent,
        applied_at=today,
        source_id=children[0].id,
        source_ids=[c.id for c in children],
        output_ids=[parent_id],
    )
    tracked_write(
        patches_dir / f"{patch.id}.md",
        serialize_patch(patch),
        kind="knowledge_patch",
        writer=_WRITER,
    )
    return parent


def _compose_summary(children: list[Node]) -> str:
    """Distill child summaries (or titles, as fallback) into one parent line."""
    return " · ".join(c.summary or c.title for c in children)


__all__ = ["ROLLUP_PATCH_KIND", "STATUS_ROLLED_UP", "rollup"]
