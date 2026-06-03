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

"""Agent working memory (knowledge face 5.2) — notes the agent writes mid-task.

The *episodic* half of agent memory: short observations / facts / decisions the
agent records **during** an interaction and recalls within (and across) the
session via the normal knowledge query. Distinct from the *semantic* durable
lessons (``recycle`` → ``knowledge/nodes``, committed): working memory lives in
``state/agents/memory/`` — **ephemeral** (survives a ``cache`` purge but is not
committed), and can be promoted to a durable lesson with ``recycle``.

See the "Two faces of knowledge" section of ``standard.knowledge-mechanism``.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Sequence


def memory_space(root: str | Path) -> Path:
    """Ensure + return the working-memory doc-space (``nodes/`` + ``patches/``)."""
    from forktex.agent.knowledge.sources import ensure_doc_space
    from forktex.substrate import paths as _sub

    return ensure_doc_space(_sub.agent_memory_dir(Path(root)))


def _note_id(note: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", note[:48].lower()).strip("-") or "note"
    digest = hashlib.sha1(note.encode("utf-8")).hexdigest()[:6]
    return f"note.{slug}-{digest}"


def _title(note: str) -> str:
    first = note.strip().splitlines()[0] if note.strip() else "note"
    return first[:80]


def remember(
    root: str | Path, note: str, *, tags: Sequence[str] = (), agent: str | None = None
) -> Any:
    """Record a working-memory note for the current project. Idempotent by content.

    Returns the written ``Node``. The note becomes recallable via the normal
    ``knowledge`` query (the memory doc-space composes as the top layer).
    """
    from forktex.agent.knowledge.recycle import recycle

    if not note or not note.strip():
        raise ValueError("remember() requires a non-empty note")
    return recycle(
        memory_space(root),
        id=_note_id(note),
        title=_title(note),
        body_md=note.strip(),
        kind="observation",
        summary=note.strip()[:200],
        tags=[*tags, "memory"],
        agent=agent or "forktex.agent.knowledge.memory",
    )


def memory_source(root: str | Path) -> tuple[str, str, str] | None:
    """A resolver ``extra_sources`` triple for the memory layer, if it has notes.

    Returns ``("memory", <dir>, "workspace")`` so working memory composes as the
    top recall layer; ``None`` when no notes exist yet (no empty layer).
    """
    from forktex.substrate import paths as _sub

    mem = _sub.agent_memory_dir(Path(root))
    nodes = mem / "nodes"
    if nodes.is_dir() and any(nodes.glob("*.md")):
        return ("memory", str(mem), "workspace")
    return None


def create_memory_tools(project_root: str | Path) -> list:
    """The ``remember`` tool — lets the agent store working-memory notes mid-task."""
    from forktex.agent.tools.base import Tool, ToolResult

    async def _remember(note: str = "", tags: list[str] | None = None) -> ToolResult:
        try:
            n = remember(project_root, note, tags=tags or [])
        except Exception as exc:
            return ToolResult(content=f"could not remember: {exc}", is_error=True)
        return ToolResult(content=f"remembered ({n.id}): {n.title}")

    return [
        Tool(
            name="remember",
            description=(
                "Store a short working-memory note (observation, fact, decision) "
                "for the current task. Recalled later via knowledge search this "
                "session. Ephemeral — promote with `recycle` to keep it durably."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "note": {"type": "string", "description": "The note to remember."},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags for recall.",
                    },
                },
                "required": ["note"],
            },
            handler=_remember,
        )
    ]


__all__ = ["memory_space", "remember", "memory_source", "create_memory_tools"]
