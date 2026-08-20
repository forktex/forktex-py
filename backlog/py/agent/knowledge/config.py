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

"""``load_knowledge_config(project_root)`` — the one entry point for runtime
configuration of the knowledge mechanism.

A ``KnowledgeConfig`` (Pydantic) lives under ``forktex.json``'s ``knowledge:``
block. When the block is absent (or the project has no ``forktex.json`` at
all), defaults apply — and the defaults preserve today's behaviour. Code that
needs to read any setting (grounding's char budget, the pinned-tag name, the
search stopword set, the layer composition) goes through this function instead
of inlining ``os.environ`` reads or hardcoded constants.

The function is best-effort: any failure to locate / parse / validate the
manifest yields a default ``KnowledgeConfig`` rather than raising. The
mechanism degrades to sane behaviour, never blocks the agent on a config bug.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — type-only; runtime import is function-local
    from forktex.manifest.models import KnowledgeConfig


def load_knowledge_config(project_root: str | Path | None = None) -> KnowledgeConfig:
    """Resolve the project's :class:`KnowledgeConfig` (with defaults on miss).

    ``project_root`` is either an explicit path or ``None`` to auto-discover via
    ``forktex.core.paths.find_project_root`` from ``os.getcwd()``. A missing
    ``forktex.json`` or a missing ``knowledge`` block both yield defaults.

    The manifest import is function-local for two reasons: (a) it sidesteps a
    pre-existing ``forktex.manifest.models`` ↔ ``forktex.fsd.loader`` circular
    that fires when ``config`` is imported before the FSD module has finished
    loading; (b) it keeps the cold-start cost off any path that never asks for
    config (search with defaults, grounding without a project manifest).
    """
    # KnowledgeConfig must be imported here, not at module top — see docstring.
    from forktex.manifest.models import KnowledgeConfig

    root = _resolve_root(project_root)
    if root is None:
        return KnowledgeConfig()
    manifest_path = root / "forktex.json"
    if not manifest_path.is_file():
        return KnowledgeConfig()

    try:
        from forktex.manifest.models import ForktexManifest

        manifest = ForktexManifest.load(manifest_path)
    except Exception:
        # Any manifest error — schema drift, unreadable file, etc. — falls back
        # to defaults rather than blocking the agent. ``forktex knowledge doctor``
        # surfaces these as actionable issues at maintenance time.
        return KnowledgeConfig()
    return manifest.knowledge or KnowledgeConfig()


def _resolve_root(explicit: str | Path | None) -> Path | None:
    if explicit is not None:
        candidate = Path(explicit)
        return candidate if candidate.is_dir() else None
    try:
        from forktex.core.paths import find_project_root

        return find_project_root()
    except Exception:
        return None


__all__ = ["load_knowledge_config"]
