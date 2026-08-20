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

"""Atomicity under concurrent recycle.

The recycle/rollup helpers now route writes through ``tracked_write`` (tempfile
+ ``os.replace``), so two concurrent writers of the *same* path see
last-writer-wins on the bytes but never a torn file. Two concurrent writers of
*different* paths see clean independent writes — both files land in full, no
``.tmp`` debris.

We don't test the *same-id contention* path because recycle's dedup re-loads the
existing node and unions tags + references: under a true race, one writer's
tag-union can be lost (the version that committed second didn't see the version
committed first). That's acceptable for v1 — the failure mode is "lost union",
not "corrupt file" — and the same-id contention test wouldn't have a stable
invariant to assert.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from forktex_core.fractal import load_node

from forktex.agent.knowledge.recycle import recycle
from forktex.agent.knowledge.rollup import STATUS_ROLLED_UP, rollup


def _doc_space(root: Path) -> Path:
    """The canonical knowledge doc-space inside a project root."""
    return root / ".forktex" / "knowledge"


@pytest.mark.parametrize("n_parallel", [4, 16])
def test_recycle_concurrent_distinct_ids(project_root, n_parallel: int) -> None:
    """N threads recycling N different node ids → all files land cleanly."""
    space = _doc_space(project_root)

    def _one(i: int) -> str:
        node_id = f"lesson.parallel-{i:03d}"
        recycle(
            space,
            id=node_id,
            title=f"Parallel lesson {i}",
            summary=f"Lesson {i}: a battle-tested observation worth recycling.",
            why=f"Because reason number {i}.",
            how_to_apply=f"Step number {i}.",
            tags=[f"batch-{i % 4}"],
            agent="concurrency-test",
        )
        return node_id

    with ThreadPoolExecutor(max_workers=min(n_parallel, 8)) as pool:
        futures = [pool.submit(_one, i) for i in range(n_parallel)]
        written_ids = {f.result() for f in as_completed(futures)}

    # Every id has exactly one node file + one patch file; no .tmp debris.
    nodes_dir = space / "nodes"
    patches_dir = space / "patches"
    node_files = sorted(p.name for p in nodes_dir.glob("*"))
    patch_files = sorted(p.name for p in patches_dir.glob("*"))
    assert all(f"{nid}.md" in node_files for nid in written_ids)
    assert all(f"patch.recycle.{nid}.md" in patch_files for nid in written_ids)
    assert not any(p.name.endswith(".tmp") for p in nodes_dir.iterdir())
    assert not any(p.name.endswith(".tmp") for p in patches_dir.iterdir())

    # Every node loads back to a coherent record (no torn writes).
    for node_id in written_ids:
        loaded = load_node(nodes_dir / f"{node_id}.md")
        assert loaded.id == node_id
        assert loaded.summary is not None
        assert "**Why:**" in loaded.body_md


def test_rollup_after_concurrent_recycle_is_consistent(project_root) -> None:
    """Recycle N children in parallel, then roll up — all demoted, parent fresh."""
    space = _doc_space(project_root)

    # Seed a parent + N children concurrently.
    recycle(space, id="topic.parallel", title="Parallel topic", summary="Parent topic.")

    child_ids = [f"lesson.par-child-{i}" for i in range(6)]

    def _one(cid: str, i: int) -> None:
        recycle(
            space,
            id=cid,
            title=f"Child {i}",
            summary=f"Child observation {i}.",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_one, child_ids, range(len(child_ids))))

    # Roll them up under the parent.
    parent = rollup(space, "topic.parallel", child_ids=child_ids)

    # Parent carries the distilled summary; every child is rolled-up; no debris.
    nodes_dir = space / "nodes"
    assert parent.summary is not None
    assert "Child observation 0" in parent.summary
    for cid in child_ids:
        loaded = load_node(nodes_dir / f"{cid}.md")
        assert loaded.status == STATUS_ROLLED_UP
    assert not any(p.name.endswith(".tmp") for p in nodes_dir.iterdir())
    assert (space / "patches" / "patch.rollup.topic.parallel.md").is_file()
