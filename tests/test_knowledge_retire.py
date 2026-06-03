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

"""Retire — the demotion path recycle's union-dedup lacks.

A retired node stays on disk and is resolvable by id, but is filtered from
grounding + default ranked-search. Pair with ``recycle --replace-tags`` to
demote a previously over-pinned standard without rewriting its content.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forktex_core.fractal import load_node

from forktex.agent.knowledge.recycle import recycle
from forktex.agent.knowledge.retire import STATUS_RETIRED, retire


def test_retire_marks_node_filtered_but_loadable(tmp_path: Path) -> None:
    space = tmp_path / ".forktex" / "knowledge"
    recycle(
        space,
        id="lesson.demote-me",
        title="A lesson that turned out wrong",
        summary="An over-pinned claim about something.",
        tags=["pinned"],
    )

    retired = retire(space, "lesson.demote-me", reason="Superseded by better evidence.")
    assert retired.status == STATUS_RETIRED
    # The node file stays on disk — audit trail intact.
    on_disk = load_node(space / "nodes" / "lesson.demote-me.md")
    assert on_disk.status == STATUS_RETIRED
    # Provenance patch records the reason in its body.
    patch_path = space / "patches" / "patch.retire.lesson.demote-me.md"
    assert patch_path.is_file()
    assert "**Reason:** Superseded by better evidence." in patch_path.read_text()


def test_retire_filters_from_grounding(tmp_path: Path) -> None:
    """A retired node should not surface in build_system_prompt's knowledge tier."""
    from forktex.agent.intelligence.grounding import _knowledge_section

    space = tmp_path / ".forktex" / "knowledge"
    recycle(
        space,
        id="standard.gone",
        title="Standard that's been retired",
        summary="Used to be pinned. No longer relevant.",
        tags=["pinned"],
    )
    recycle(
        space,
        id="standard.kept",
        title="Standard still in force",
        summary="Battle-tested; pinned.",
        tags=["pinned"],
    )

    # Before retirement: both visible in grounding.
    section_before = _knowledge_section(tmp_path)
    assert section_before is not None
    assert "standard.gone" in section_before
    assert "standard.kept" in section_before

    retire(space, "standard.gone", reason="Replaced by standard.kept.")

    # After retirement: gone-id silent, kept-id still pinned.
    section_after = _knowledge_section(tmp_path)
    assert section_after is not None
    assert "standard.gone" not in section_after
    assert "standard.kept" in section_after


def test_recycle_replace_tags_drops_existing(tmp_path: Path) -> None:
    """The demotion path: re-recycle with --replace-tags to actually drop a tag."""
    space = tmp_path / "ds"
    recycle(space, id="lesson.over-pinned", title="Was pinned", tags=["pinned", "stale"])

    # Default (union) — pinned would stick around.
    refined_union = recycle(space, id="lesson.over-pinned", title="Was pinned", tags=["fresh"])
    assert set(refined_union.tags) == {"pinned", "stale", "fresh"}

    # Explicit replace — only the new tags remain.
    refined_replace = recycle(
        space,
        id="lesson.over-pinned",
        title="Was pinned",
        tags=["fresh"],
        replace_tags=True,
    )
    assert set(refined_replace.tags) == {"fresh"}


def test_recycle_replace_refs_drops_existing(tmp_path: Path) -> None:
    space = tmp_path / "ds"
    recycle(space, id="n.refs", title="With refs", references=["a", "b"])
    union = recycle(space, id="n.refs", title="With refs", references=["c"])
    assert set(union.references) == {"a", "b", "c"}
    replace = recycle(
        space, id="n.refs", title="With refs", references=["c"], replace_refs=True
    )
    assert set(replace.references) == {"c"}


def test_retire_unknown_id_raises(tmp_path: Path) -> None:
    space = tmp_path / "ds"
    (space / "nodes").mkdir(parents=True)
    with pytest.raises(KeyError):
        retire(space, "nope")
