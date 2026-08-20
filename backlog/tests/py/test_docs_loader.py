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

"""The docs-corpus loader must surface on-disk ``summary:`` + ``tags:`` from real
docs files — which all open with a license-header HTML comment before the YAML
frontmatter. Regression check for the silent fall-back that hid the entire
on-disk frontmatter behind manifest-only data.
"""

from __future__ import annotations

import json
from pathlib import Path

from forktex.agent.knowledge.sources import load_docs_corpus


_HEADER = """<!--
  Copyright (C) 2026 FORKTEX S.R.L.

  TRADE SECRET -- STRICTLY CONFIDENTIAL AND PROPRIETARY
-->

"""


def _doc(fm_block: str, body: str = "") -> str:
    """A docs file: license-header HTML comment, then YAML frontmatter, then body."""
    return f"{_HEADER}---\n{fm_block}\n---\n\n{body}"


def test_docs_loader_reads_on_disk_summary_and_pinned_tags(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "engineering" / "standards").mkdir(parents=True)
    (docs / "engineering" / "standards" / "qp.md").write_text(
        _doc(
            "id: standard.quality-pipeline\n"
            "slug: quality-pipeline\n"
            "kind: standard\n"
            "title: Quality Pipeline\n"
            "summary: Battle-test against real testcontainers; never mock infra.\n"
            "tags: [pinned]\n"
            "updated: 2026-05-25\n"
            "status: active\n"
            "version: 1.0.0\n"
        )
    )
    (docs / "engineering" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-28",
                "items": [
                    {
                        "id": "standard.quality-pipeline",
                        "slug": "quality-pipeline",
                        "kind": "standard",
                        "title": "Quality Pipeline (manifest title — should NOT win over fm)",
                        "path": "docs/engineering/standards/qp.md",
                        "status": "active",
                        "updated": "2026-03-11",
                        "version": "1.0.0",
                    }
                ],
            }
        )
    )

    ws = load_docs_corpus(docs)
    node = ws.nodes["standard.quality-pipeline"]

    # Summary + pinned tag from the on-disk frontmatter (would silently be lost
    # without the HTML-header strip + the summary read in _build_node).
    assert node.summary == "Battle-test against real testcontainers; never mock infra."
    assert "pinned" in node.tags
    # On-disk title wins over manifest title (the file is the freshest source).
    assert node.title == "Quality Pipeline"
    # On-disk updated_at wins over the stale manifest date.
    assert node.updated_at == "2026-05-25"
