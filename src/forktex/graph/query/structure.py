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

"""Structure-spec / registry / write-history queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from forktex.graph import structure as _structure
from forktex.graph.registry import load as _load_registry
from forktex.models.base import ForkTexModel


class StructureMatch(ForkTexModel):
    rel_path: str
    ok: bool
    pattern: str = ""
    purpose: str = ""
    sensitivity: str = ""
    reason: str = ""


class Touch(ForkTexModel):
    project_root: str
    rel_path: str
    kind: str
    writer: str | None = None
    last_touched_at: str


def validate_path(rel_path: str, scope: str = "project") -> StructureMatch:
    """Match *rel_path* (relative to ``.forktex/``) against the canonical
    structure spec and return a structured result.

    Wraps ``forktex.graph.structure.validate_path`` to expose a JSON-friendly
    result for tool callers.
    """
    result = _structure.validate_path(scope, rel_path)  # type: ignore[arg-type]
    spec = result.spec
    return StructureMatch(
        rel_path=rel_path,
        ok=result.ok,
        pattern=spec.pattern if spec else "",
        purpose=spec.purpose if spec else "",
        sensitivity=spec.sensitivity if spec else "",
        reason=result.reason,
    )


def writers_for_path(rel_path: str, scope: str = "project") -> list[str]:
    """Authorised writer modules declared in the spec for *rel_path*."""
    result = _structure.validate_path(scope, rel_path)  # type: ignore[arg-type]
    if not result.ok or result.spec is None:
        return []
    return list(result.spec.writers)


# ── Registry / write history ─────────────────────────────────────────────


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def files_touched_recently(
    project_root: Path | None = None, hours: int = 24
) -> list[Touch]:
    """Files inside ``.forktex/`` touched in the last *hours*, with attribution.

    Reads from ``~/.forktex/registry.json`` (the OS-wide write log). Pass
    ``project_root`` to filter to a single project; ``None`` returns
    touches across every registered project.
    """
    reg = _load_registry()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out: list[Touch] = []

    target_roots: set[str] | None = None
    if project_root is not None:
        target_roots = {str(project_root.resolve())}

    for proj in reg.projects.values():
        if target_roots is not None and proj.root not in target_roots:
            continue
        for t in proj.touches:
            ts = _parse_iso(t.last_touched_at)
            if ts is None or ts < cutoff:
                continue
            out.append(
                Touch(
                    project_root=proj.root,
                    rel_path=t.rel_path,
                    kind=t.kind,
                    writer=t.writer,
                    last_touched_at=t.last_touched_at,
                )
            )

    # Global touches (writes inside ~/.forktex/) — only when no project filter.
    if target_roots is None:
        for t in reg.global_touches:
            ts = _parse_iso(t.last_touched_at)
            if ts is None or ts < cutoff:
                continue
            out.append(
                Touch(
                    project_root="<global>",
                    rel_path=t.rel_path,
                    kind=t.kind,
                    writer=t.writer,
                    last_touched_at=t.last_touched_at,
                )
            )
    return sorted(out, key=lambda x: x.last_touched_at, reverse=True)
