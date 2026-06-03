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

"""``resolve_doc_space`` normalizes a ``--project`` value to ``.forktex/knowledge``.

Regression guard: pointing recycle/retire/rollup's ``-d`` at a *repo root*
(``.``, a project dir) used to create stray top-level ``nodes/``/``patches/``,
because the value was handed verbatim to ``ensure_doc_space``. The resolver
derives the doc-space, so a repo root can never pollute the project root again.
"""

from __future__ import annotations

import json
from pathlib import Path

from forktex.agent.knowledge.recycle import recycle
from forktex.agent.knowledge.sources import (
    ensure_doc_space,
    project_doc_space,
    resolve_doc_space,
)


def test_repo_root_resolves_to_doc_space(tmp_path: Path) -> None:
    (tmp_path / "forktex.json").write_text(json.dumps({"name": "demo"}))
    assert resolve_doc_space(tmp_path) == project_doc_space(tmp_path)


def test_repo_root_detected_by_dotforktex(tmp_path: Path) -> None:
    (tmp_path / ".forktex").mkdir()
    assert resolve_doc_space(tmp_path) == project_doc_space(tmp_path)


def test_existing_doc_space_is_unchanged(tmp_path: Path) -> None:
    space = tmp_path / ".forktex" / "knowledge"
    space.mkdir(parents=True)
    assert resolve_doc_space(space) == space


def test_plain_dir_is_back_compat_passthrough(tmp_path: Path) -> None:
    # No .forktex, no forktex.json — an explicit doc-space dir not under a repo.
    plain = tmp_path / "some_space"
    plain.mkdir()
    assert resolve_doc_space(plain) == plain


def test_recycle_with_repo_root_lands_in_doc_space_not_root(tmp_path: Path) -> None:
    (tmp_path / "forktex.json").write_text(json.dumps({"name": "demo"}))

    # Mirror what recycle_cmd does with an explicit -d pointing at the repo root.
    target = ensure_doc_space(resolve_doc_space(tmp_path))
    node = recycle(target, id="lesson.guard", title="guard", summary="x", agent="test")

    assert (tmp_path / ".forktex" / "knowledge" / "nodes" / f"{node.id}.md").is_file()
    # The bug we fixed: NO stray nodes/patches at the repo root.
    assert not (tmp_path / "nodes").exists()
    assert not (tmp_path / "patches").exists()
