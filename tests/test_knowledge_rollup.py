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

"""Rollup compacts a resolved subtree into the parent's summary and demotes the
children — bounded working set, the fractal-of-fractals analogue of context
compaction. Filesystem round-trip only.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from forktex_core.fractal import load_node

from forktex.agent.knowledge.recycle import recycle
from forktex.agent.knowledge.rollup import STATUS_ROLLED_UP, rollup


def _seed_subtree(space: Path) -> None:
    recycle(space, id="topic.async-io", title="Async IO Topic", summary="Parent topic.")
    recycle(
        space,
        id="lesson.no-blocking",
        title="No blocking calls",
        summary="Never call blocking IO inside the event loop.",
        references=["topic.async-io"],
        kind="lesson",
    )
    # `parent` edges are how the engine derives children (via the graph).
    from forktex_core.fractal import Node
    from forktex_core.fractal.io import dump_node as _dump

    today = date.today().isoformat()
    for cid, cprose in [
        ("lesson.use-async-drivers", "Always use async drivers (asyncpg, httpx)."),
        ("lesson.no-time-sleep", "Use asyncio.sleep, never time.sleep, inside coroutines."),
    ]:
        node = Node(
            id=cid,
            kind="lesson",
            title=cid,
            summary=cprose,
            updated_at=today,
            parents=["topic.async-io"],
        )
        _dump(node, space / "nodes" / f"{cid}.md")


def test_rollup_compacts_children_into_parent_summary(tmp_path: Path) -> None:
    space = tmp_path / ".forktex" / "knowledge"
    _seed_subtree(space)

    parent = rollup(space, "topic.async-io")

    assert parent.summary is not None
    # Auto-composed summary distills the children's summaries.
    assert "Always use async drivers" in parent.summary
    assert "asyncio.sleep, never time.sleep" in parent.summary
    assert parent.updated_at == date.today().isoformat()  # freshness stamped

    # Children are demoted on disk: status='rolled-up' is the retrieval signal.
    for cid in ("lesson.use-async-drivers", "lesson.no-time-sleep"):
        child = load_node(space / "nodes" / f"{cid}.md")
        assert child.status == STATUS_ROLLED_UP

    # Provenance patch written — the rollup is auditable.
    assert (space / "patches" / "patch.rollup.topic.async-io.md").is_file()


def test_rollup_accepts_explicit_summary_and_child_ids(tmp_path: Path) -> None:
    space = tmp_path / "ds"
    _seed_subtree(space)

    parent = rollup(
        space,
        "topic.async-io",
        summary="All IO is async; never block the loop.",
        child_ids=["lesson.use-async-drivers"],  # explicit subset
    )

    assert parent.summary == "All IO is async; never block the loop."
    # Only the listed child was demoted; the other stays active.
    assert load_node(space / "nodes" / "lesson.use-async-drivers.md").status == STATUS_ROLLED_UP
    assert load_node(space / "nodes" / "lesson.no-time-sleep.md").status != STATUS_ROLLED_UP


def test_rollup_errors_when_no_children(tmp_path: Path) -> None:
    space = tmp_path / "ds"
    recycle(space, id="lonely.parent", title="Lonely")
    with pytest.raises(ValueError):
        rollup(space, "lonely.parent")


def test_rollup_errors_on_missing_parent(tmp_path: Path) -> None:
    space = tmp_path / "ds"
    (space / "nodes").mkdir(parents=True)
    with pytest.raises(KeyError):
        rollup(space, "nope")
