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

"""``forktex knowledge init`` — one-command bootstrap of the knowledge mechanism.

Scaffolds the project doc-space (``.forktex/knowledge/{nodes,patches}/``) plus a
short README and, when ``forktex.json`` is present, appends an explicit
``knowledge`` block with the v1 defaults — the discoverable form, so a reader of
the manifest can see every knob, even when none have been customised.

After running this, ``forktex knowledge search`` / ``recycle`` / ``rollup`` /
``retire`` work in the project, and any agent grounded via ``forktex knowledge
mcp`` or ``build_system_prompt`` composes the global docs corpus with this
project's local knowledge.

Init also runs the standard ``.forktex/`` lifecycle bootstrap so the directory
it creates is spec-compliant from the first write: ``.version`` + the
defence-in-depth ``.gitignore`` are present, exactly as a full forktex
invocation would leave them.
"""

from __future__ import annotations

import json
from pathlib import Path

from forktex.agent.knowledge.sources import ensure_doc_space, project_doc_space
from forktex.graph.io_proxy import tracked_write
from forktex.runtime import lifecycle

#: Minimal stub seeded into ``forktex.json[knowledge]`` on init — explicit
#: defaults for discoverability. Matches the ``KnowledgeConfig`` v1 defaults.
_DEFAULT_KNOWLEDGE_BLOCK: dict[str, object] = {
    "pinnedTag": "pinned",
    "groundingCharBudget": 4000,
    "knowledgeLimit": 40,
    "retiredStatuses": ["retired", "rolled-up"],
}

_README_TEMPLATE = """# Project knowledge

This directory is the project's **knowledge doc-space** — the recycle
write-target + the layer that composes onto the global `docs/` corpus for
agent grounding.

## Workflow

- Query: `forktex knowledge search "<topic>"` — searches the composed view
  (global docs ← this project's overlay).
- Recycle a lesson:
  ```
  forktex knowledge recycle lesson.<short-id> \\
      --title "..." --summary "..." \\
      --why "..." --how "..." --tag pattern
  ```
- Promote a must-follow standard: add `--tag pinned` (always-inject).
- Demote / retire: `forktex knowledge retire <id> --reason "..."` (audit-only;
  the node stays on disk but is filtered from grounding + ranked search).
- Compact a resolved subtree: `forktex knowledge rollup <parent_id>`.

## Layout

- `nodes/<id>.md` — one frontmatter-markdown file per knowledge node.
- `patches/<id>.md` — provenance patches (recycle / rollup / retire trail).

Both are tracked via `forktex.graph.io_proxy.tracked_write` (atomic tempfile
+ os.replace). Writes are per-file atomic; consider this directory part of
the project's source-of-truth and commit it alongside code (or .gitignore
it for per-developer notes — your call).
"""


class InitResult:
    """What ``init_doc_space`` did, returned for CLI rendering + tests."""

    __slots__ = ("doc_space", "created_dirs", "created_readme", "added_manifest_block")

    def __init__(
        self,
        doc_space: Path,
        created_dirs: bool,
        created_readme: bool,
        added_manifest_block: bool,
    ) -> None:
        self.doc_space = doc_space
        self.created_dirs = created_dirs
        self.created_readme = created_readme
        self.added_manifest_block = added_manifest_block


def init_doc_space(
    project_root: str | Path,
    *,
    with_readme: bool = True,
    with_manifest_block: bool = True,
) -> InitResult:
    """Scaffold the project doc-space + optionally seed ``forktex.json``.

    Idempotent: missing dirs are created; an existing README is left alone; a
    pre-existing ``knowledge`` block in ``forktex.json`` is preserved (we never
    overwrite user-customised config). Returns a summary of what changed.
    """
    root = Path(project_root).resolve()
    # Bootstrap .version + the inner .gitignore before scaffolding, or a
    # knowledge-only init leaves a .forktex/ that fails its own structure audit.
    lifecycle.install_project(root)

    space = project_doc_space(root)
    existed = (space / "nodes").is_dir() and (space / "patches").is_dir()
    ensure_doc_space(space)
    created_dirs = not existed

    readme_path = space / "README.md"
    created_readme = False
    if with_readme and not readme_path.is_file():
        tracked_write(
            readme_path,
            _README_TEMPLATE,
            kind="knowledge_readme",
            writer="forktex.agent.knowledge.init",
        )
        created_readme = True

    added_manifest_block = False
    manifest_path = root / "forktex.json"
    if with_manifest_block and manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = None
        if isinstance(manifest, dict) and "knowledge" not in manifest:
            manifest["knowledge"] = dict(_DEFAULT_KNOWLEDGE_BLOCK)
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            added_manifest_block = True

    return InitResult(
        doc_space=space,
        created_dirs=created_dirs,
        created_readme=created_readme,
        added_manifest_block=added_manifest_block,
    )


__all__ = ["InitResult", "init_doc_space"]
