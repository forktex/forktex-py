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

"""The recycle write-back loop: a learning captured this session is queryable the
next (anti-amnesia), deduped by id, surfaced over the tool + grounding surfaces.

Filesystem round-trip only — no Postgres/Qdrant — since recycle is pure markdown
persistence over the core ``fractal.io`` primitives.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from forktex_core.fractal import FractalQuery, load_node

from forktex.agent.knowledge.recycle import recycle
from forktex.agent.knowledge.search import ranked_search
from forktex.agent.knowledge.sources import (
    COMPOSED_NAMESPACE,
    build_knowledge_resolver,
)
from forktex.agent.knowledge.tools import build_knowledge_tools


def test_recycle_writes_actionable_node(tmp_path: Path) -> None:
    space = tmp_path / ".forktex" / "knowledge"
    node = recycle(
        space,
        id="lesson.testcontainers",
        title="Test against real infra",
        summary="Use testcontainers Postgres/Qdrant; never mock infrastructure.",
        kind="lesson",
        why="Mocks drift from real backends and hide integration bugs.",
        how_to_apply="Spin a testcontainer in the fixture; assert against it.",
        tags=["pinned", "testing"],
        agent="test",
    )

    assert node.id == "lesson.testcontainers"
    assert node.updated_at == date.today().isoformat()  # freshness stamped
    on_disk = load_node(space / "nodes" / "lesson.testcontainers.md")
    assert "**Why:** Mocks drift" in on_disk.body_md
    assert "**How to apply:** Spin a testcontainer" in on_disk.body_md
    assert "pinned" in on_disk.tags
    # A provenance patch was written alongside.
    assert (space / "patches" / "patch.recycle.lesson.testcontainers.md").is_file()


def test_recycle_dedups_and_unions(tmp_path: Path) -> None:
    space = tmp_path / "ds"
    recycle(space, id="n.dedup", title="First", tags=["a"], references=["x"])
    recycle(space, id="n.dedup", title="Refined", tags=["b"], references=["y"])

    files = list((space / "nodes").glob("*.md"))
    assert len(files) == 1  # dedup by id — one file, not two
    refined = load_node(files[0])
    assert refined.title == "Refined"
    assert set(refined.tags) == {"a", "b"}  # unioned
    assert set(refined.references) == {"x", "y"}


def test_recycled_node_is_queryable_next_session(tmp_path: Path) -> None:
    """Session 1 recycles; session 2 (fresh resolver) finds it — the compounding loop."""
    space = tmp_path / ".forktex" / "knowledge"
    recycle(
        space,
        id="lesson.async-first",
        title="Async-first IO",
        summary="All IO-bound code is async; no blocking calls in the event loop.",
        why="Blocking calls stall the loop under concurrency.",
        how_to_apply="Use async drivers; await IO.",
    )

    # A brand-new resolver (as a later session would build) sees it on disk.
    resolver = build_knowledge_resolver(project_path=space)
    query = FractalQuery(resolver)
    hits = ranked_search(query, COMPOSED_NAMESPACE, "async blocking event loop", limit=5)
    assert any(h.id == "lesson.async-first" for h in hits)

    detail = query.get_node(COMPOSED_NAMESPACE, "lesson.async-first").node
    assert "**How to apply:** Use async drivers" in detail.body_md


async def test_recycle_tool_round_trips(tmp_path: Path) -> None:
    space = tmp_path / "ds"
    space.mkdir()
    (space / "nodes").mkdir()
    resolver = build_knowledge_resolver(project_path=space)
    query = FractalQuery(resolver)

    tools = {t.name: t for t in build_knowledge_tools(query, recycle_dir=space)}
    assert "knowledge_recycle" in tools  # only present when a recycle target is set

    result = await tools["knowledge_recycle"].execute(
        id="lesson.commit-msgs",
        title="Conventional commits",
        summary="Commit subjects are imperative, <=50 chars.",
        why="Consistent history is greppable and changelog-able.",
        how_to_apply="Write 'Add X' not 'Added X'.",
        tags=["pinned"],
    )
    assert not result.is_error
    assert json.loads(result.content)["recycled"] == "lesson.commit-msgs"

    # Same query surface now finds the just-written node (mtime reload).
    found = ranked_search(query, COMPOSED_NAMESPACE, "commit imperative greppable", limit=5)
    assert any(h.id == "lesson.commit-msgs" for h in found)


def test_grounding_surfaces_pinned_with_summary(tmp_path: Path) -> None:
    from forktex.agent.intelligence.grounding import _knowledge_section

    space = tmp_path / ".forktex" / "knowledge"
    recycle(
        space,
        id="standard.no-mocks",
        title="No infra mocks",
        summary="Battle-test against real containers; never mock infrastructure.",
        tags=["pinned"],
    )
    recycle(space, id="note.misc", title="A non-pinned note", summary="Just an index entry.")

    section = _knowledge_section(tmp_path)
    assert section is not None
    assert "Always follow these (pinned)" in section
    assert "Battle-test against real containers" in section  # pinned → full summary
    assert "standard.no-mocks" in section
    # Non-pinned appears in the cheap index tier (id/title), not as a pinned summary.
    assert "note.misc" in section
