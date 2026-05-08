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

"""Authoritative index of project roots that ForkTex has touched.

Lives at ``~/.forktex/registry.json`` (cross-platform via
:func:`forktex_cloud.paths.global_dir`). Every write that
:mod:`forktex.graph.io_proxy` performs into a ``.forktex/`` directory is
appended here as a :class:`Touch`. The registry is the answer to
"what would ``forktex graph purge --scope all`` actually delete?".

Concurrency: writes use a tempfile + atomic rename; the rare race window
where two processes append simultaneously is acceptable because every
entry is keyed by ``(root, rel_path)`` — the merge in :func:`record_touch`
deduplicates.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from forktex_cloud import paths as _cloud_paths


REGISTRY_FILENAME = "registry.json"
REGISTRY_SCHEMA_VERSION = 1

_lock = threading.Lock()


# ── Models ────────────────────────────────────────────────────────────────


@dataclass
class Touch:
    rel_path: str
    kind: str
    writer: str | None
    last_touched_at: str


@dataclass
class RegisteredProject:
    root: str
    first_seen_at: str
    last_touched_at: str
    touches: list[Touch] = field(default_factory=list)


@dataclass
class Registry:
    schema_version: int = REGISTRY_SCHEMA_VERSION
    projects: dict[str, RegisteredProject] = field(default_factory=dict)
    global_touches: list[Touch] = field(default_factory=list)


# ── Path ──────────────────────────────────────────────────────────────────


def registry_path() -> Path:
    return _cloud_paths.global_dir() / REGISTRY_FILENAME


# ── Serialisation ─────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_dict(reg: Registry) -> dict:
    return {
        "schema_version": reg.schema_version,
        "projects": [
            {
                "root": p.root,
                "first_seen_at": p.first_seen_at,
                "last_touched_at": p.last_touched_at,
                "touches": [asdict(t) for t in p.touches],
            }
            for p in sorted(reg.projects.values(), key=lambda r: r.root)
        ],
        "global_touches": [asdict(t) for t in reg.global_touches],
    }


def _from_dict(payload: dict) -> Registry:
    projects: dict[str, RegisteredProject] = {}
    for entry in payload.get("projects", []) or []:
        root = entry.get("root")
        if not root:
            continue
        projects[root] = RegisteredProject(
            root=root,
            first_seen_at=entry.get("first_seen_at", _now_iso()),
            last_touched_at=entry.get("last_touched_at", _now_iso()),
            touches=[
                Touch(
                    rel_path=t.get("rel_path", ""),
                    kind=t.get("kind", "unknown"),
                    writer=t.get("writer"),
                    last_touched_at=t.get("last_touched_at", _now_iso()),
                )
                for t in entry.get("touches", []) or []
            ],
        )
    return Registry(
        schema_version=int(payload.get("schema_version", REGISTRY_SCHEMA_VERSION)),
        projects=projects,
        global_touches=[
            Touch(
                rel_path=t.get("rel_path", ""),
                kind=t.get("kind", "unknown"),
                writer=t.get("writer"),
                last_touched_at=t.get("last_touched_at", _now_iso()),
            )
            for t in payload.get("global_touches", []) or []
        ],
    )


# ── Read / write ──────────────────────────────────────────────────────────


def load() -> Registry:
    path = registry_path()
    if not path.is_file():
        return Registry()
    try:
        return _from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):  # fmt: skip
        return Registry()


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".registry.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save(reg: Registry) -> None:
    _cloud_paths.ensure_global_dir()
    _atomic_write(registry_path(), _to_dict(reg))


# ── Mutation ──────────────────────────────────────────────────────────────


def _upsert_touch(touches: list[Touch], new: Touch) -> None:
    for i, existing in enumerate(touches):
        if existing.rel_path == new.rel_path:
            touches[i] = Touch(
                rel_path=new.rel_path,
                kind=new.kind or existing.kind,
                writer=new.writer or existing.writer,
                last_touched_at=new.last_touched_at,
            )
            return
    touches.append(new)


def record_touch(
    *,
    project_root: Path | None,
    rel_path: str,
    kind: str,
    writer: str | None = None,
    timestamp: str | None = None,
) -> None:
    """Record a write into a ``.forktex/`` directory.

    ``project_root`` is the absolute project root. Pass ``None`` to record a
    write into the global ``~/.forktex/`` directory.
    """

    ts = timestamp or _now_iso()
    touch = Touch(rel_path=rel_path, kind=kind, writer=writer, last_touched_at=ts)
    with _lock:
        reg = load()
        if project_root is None:
            _upsert_touch(reg.global_touches, touch)
        else:
            root_str = str(project_root.resolve())
            existing = reg.projects.get(root_str)
            if existing is None:
                existing = RegisteredProject(
                    root=root_str,
                    first_seen_at=ts,
                    last_touched_at=ts,
                    touches=[],
                )
                reg.projects[root_str] = existing
            existing.last_touched_at = ts
            _upsert_touch(existing.touches, touch)
        save(reg)


def forget_project(root: Path) -> bool:
    """Remove a project from the registry. Returns True if it existed."""
    with _lock:
        reg = load()
        existed = str(root.resolve()) in reg.projects
        reg.projects.pop(str(root.resolve()), None)
        save(reg)
        return existed


def iter_registered_projects() -> Iterable[RegisteredProject]:
    return list(load().projects.values())


def reconcile_existence() -> tuple[list[RegisteredProject], list[RegisteredProject]]:
    """Split registered projects into ``(present, missing)`` based on
    whether ``root`` still exists on disk. Read-only — does not mutate."""
    present: list[RegisteredProject] = []
    missing: list[RegisteredProject] = []
    for proj in iter_registered_projects():
        (present if Path(proj.root).is_dir() else missing).append(proj)
    return present, missing
