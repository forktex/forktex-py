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

"""Retire — mark a knowledge node as superseded (the demotion path recycle lacks).

``recycle`` dedups by union: re-recycling a node merges new tags / references
into the existing record. That's right for accretive refinement, wrong for
"this lesson was over-pinned" or "this convention is no longer how we work."
Retire is the explicit demotion: set ``status="retired"`` on the existing node
(the file stays on disk for audit + ``knowledge show``), stamp ``updated_at``,
and write a provenance patch. The grounding tier + ranked_search filter
``status="retired"`` by default — so the retired node is silent in agent
context but resolvable by id.

For symmetry with recycle, retire goes through ``tracked_write`` (atomic) and
uses ``serialize_node`` / ``serialize_patch`` from core 2.4.0.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from forktex_core.fractal import (
    Node,
    Patch,
    load_node,
    serialize_node,
    serialize_patch,
)

from forktex.graph.io_proxy import tracked_write

RETIRE_PATCH_KIND = "retire"
STATUS_RETIRED = "retired"

_WRITER = "forktex.agent.knowledge.retire"


def retire(
    doc_space: str | Path,
    node_id: str,
    *,
    reason: str | None = None,
    agent: str | None = None,
) -> Node:
    """Mark ``node_id`` retired in ``doc_space``; write a provenance patch.

    Raises ``KeyError`` if the node doesn't exist. Idempotent for an already-
    retired node (re-stamps ``updated_at`` and writes a fresh patch — useful for
    refreshing the reason). Returns the retired node.
    """
    space = Path(doc_space)
    nodes_dir = space / "nodes"
    patches_dir = space / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)

    node_path = nodes_dir / f"{node_id}.md"
    if not node_path.is_file():
        raise KeyError(f"node {node_id!r} not found in {space}")
    node = load_node(node_path)

    today = date.today().isoformat()
    patch_id = f"patch.retire.{node_id}"
    node.status = STATUS_RETIRED
    node.updated_at = today
    node.provenance_patch_id = patch_id
    tracked_write(node_path, serialize_node(node), kind="knowledge_node", writer=_WRITER)

    patch = Patch(
        id=patch_id,
        kind=RETIRE_PATCH_KIND,
        title=f"retire {node_id}" + (f" — {reason}" if reason else ""),
        agent=agent,
        applied_at=today,
        source_id=node_id,
        source_ids=[node_id],
        output_ids=[node_id],
        body_md=(f"**Reason:** {reason.strip()}\n" if reason else ""),
    )
    tracked_write(
        patches_dir / f"{patch_id}.md",
        serialize_patch(patch),
        kind="knowledge_patch",
        writer=_WRITER,
    )
    return node


__all__ = ["RETIRE_PATCH_KIND", "STATUS_RETIRED", "retire"]
