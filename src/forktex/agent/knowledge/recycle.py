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

"""Recycle — capture a learning back into the project doc-space (the write half).

Policy + ergonomics over the core primitives (``Node`` / ``Patch`` /
``fractal.io``): a learning becomes a retrievable node carrying its *why* +
*how-to-apply* (the bit that makes it actionable), plus a provenance ``Patch``.
**Dedup by id** — re-recycling refines the node (unions tags/references) rather
than duplicating. Written to the project doc-space so the next compose/index
picks it up: that's the compounding loop across sessions.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from forktex_core.fractal import (
    Node,
    Patch,
    load_node,
    node_from_frontmatter,
    serialize_node,
    serialize_patch,
)

from forktex.graph.io_proxy import tracked_write

RECYCLE_PATCH_KIND = "recycle"

#: Tracked-write writer identity — recorded in the ``.forktex/registry`` so each
#: node/patch on disk knows which runtime path produced it.
_WRITER = "forktex.agent.knowledge.recycle"


def recycle(
    doc_space: str | Path,
    *,
    id: str,
    title: str,
    body_md: str = "",
    kind: str = "lesson",
    summary: str | None = None,
    references: Sequence[str] = (),
    source_ids: Sequence[str] = (),
    why: str | None = None,
    how_to_apply: str | None = None,
    tags: Sequence[str] = (),
    agent: str | None = None,
    replace_tags: bool = False,
    replace_refs: bool = False,
) -> Node:
    """Write/refine a learning node (+ provenance patch) into ``doc_space``.

    ``doc_space`` is a fractal workspace dir (``nodes/`` + ``patches/`` created as
    needed). Dedup by ``id``: an existing node is refined; else inserted. Stamps
    ``updated_at`` today (freshness). Returns the written node.

    By default, ``tags`` and ``references`` *union* with the existing node — the
    accretive refinement path that's right for "I learned something new about
    this." For the demotion path ("drop a tag", "swap references"), pass
    ``replace_tags=True`` / ``replace_refs=True`` to replace instead of union.
    (Closing the gap that prompted ``lesson.recycle-dedup-is-union-only``.)
    """
    space = Path(doc_space)
    nodes_dir = space / "nodes"
    patches_dir = space / "patches"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    patches_dir.mkdir(parents=True, exist_ok=True)

    body = _compose_body(body_md, why, how_to_apply)
    refs = list(references)
    tag_list = list(tags)

    node_path = nodes_dir / f"{id}.md"
    if node_path.is_file():  # dedup → refine in place
        existing = load_node(node_path)
        title = title or existing.title
        summary = summary if summary is not None else existing.summary
        body = body or existing.body_md
        if not replace_tags:
            tag_list = list(dict.fromkeys([*existing.tags, *tag_list]))
        if not replace_refs:
            refs = list(dict.fromkeys([*existing.references, *refs]))

    patch_id = f"patch.recycle.{id}"
    today = date.today().isoformat()
    node = node_from_frontmatter(
        {
            "id": id,
            "kind": kind,
            "title": title,
            "summary": summary,
            "updated_at": today,
            "references": refs,
            "tags": tag_list,
            "provenance_patch_id": patch_id,
        },
        body,
    )
    # Atomic write (tempfile + os.replace) via tracked_write, so a concurrent
    # reader of the same path never sees a half-written file and a registry
    # record links the disk artefact back to this writer.
    tracked_write(node_path, serialize_node(node), kind="knowledge_node", writer=_WRITER)

    patch = Patch(
        id=patch_id,
        kind=RECYCLE_PATCH_KIND,
        title=f"recycle {id}",
        agent=agent,
        applied_at=today,
        source_id=(source_ids[0] if source_ids else id),
        source_ids=list(source_ids),
        output_ids=[id],
    )
    tracked_write(
        patches_dir / f"{patch_id}.md",
        serialize_patch(patch),
        kind="knowledge_patch",
        writer=_WRITER,
    )
    return node


def _compose_body(body_md: str, why: str | None, how_to_apply: str | None) -> str:
    parts = [body_md.strip()] if body_md.strip() else []
    if why:
        parts.append(f"**Why:** {why.strip()}")
    if how_to_apply:
        parts.append(f"**How to apply:** {how_to_apply.strip()}")
    return "\n\n".join(parts)


__all__ = ["RECYCLE_PATCH_KIND", "recycle"]
