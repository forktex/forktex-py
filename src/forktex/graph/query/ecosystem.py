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

"""Cross-project / OS-scope queries.

Each function walks projects under a base directory, builds (or reuses
the cached) per-project graph, and aggregates the answer.
"""

from __future__ import annotations

from pathlib import Path

from forktex.core.paths import find_projects
from forktex.graph.query.cache import session_graph
from forktex.graph.query.fsd import fsd_level_of_package
from forktex.graph.query.project import list_packages
from forktex.models.base import ForkTexModel


class EcosystemRow(ForkTexModel):
    project_name: str
    project_root: str
    fsd_level: str = "L0"
    package_count: int = 0
    domain_count: int = 0
    module_count: int = 0
    has_makefile: bool = False


class ProjectDep(ForkTexModel):
    project_name: str
    project_root: str
    package_id: str
    package_name: str
    target_name: str
    target_kind: str  # "library" | "package" | "module" | "external_dep"


class VersionRange(ForkTexModel):
    name: str
    min_version: str = ""
    max_version: str = ""
    versions: list[str] = []
    projects: list[str] = []


def _candidates(base_dir: Path, include_nested: bool) -> list[Path]:
    cands = list(find_projects(base_dir))
    if include_nested:
        for child in list(cands):
            for grand in child.iterdir() if child.is_dir() else []:
                if grand.is_dir() and (grand / "forktex.json").is_file():
                    cands.append(grand)
    return sorted({c.resolve() for c in cands})


def ecosystem_fsd_matrix(
    base_dir: Path, include_nested: bool = False
) -> list[EcosystemRow]:
    """One row per project under *base_dir* with FSD level + counts."""
    out: list[EcosystemRow] = []
    for project_root in _candidates(base_dir, include_nested):
        try:
            graph = session_graph(project_root)
        except Exception:  # pragma: no cover
            continue
        statuses = fsd_level_of_package(graph)
        # Use the root-most package's level, else the highest seen.
        level = "L0"
        if statuses:
            root_status = next(
                (s for s in statuses if s.rel_path in {".", ""}), statuses[0]
            )
            level = root_status.fsd_level
        out.append(
            EcosystemRow(
                project_name=project_root.name,
                project_root=str(project_root),
                fsd_level=level,
                package_count=len(graph.by_kind("package")),
                domain_count=len(graph.by_kind("domain")),
                module_count=len(graph.by_kind("module")),
                has_makefile=any(
                    p.attrs.get("has_makefile") for p in graph.by_kind("package")
                ),
            )
        )
    return out


def reverse_dependents(
    name: str, base_dir: Path, include_nested: bool = False
) -> list[ProjectDep]:
    """Find every project under *base_dir* whose graph references *name* as
    a library or package dependency.

    Walks each project's graph and records ``depends_on`` + ``imports``
    edges whose target name matches.
    """
    out: list[ProjectDep] = []
    for project_root in _candidates(base_dir, include_nested):
        try:
            graph = session_graph(project_root)
        except Exception:  # pragma: no cover
            continue
        # depends_on edges (declared library deps).
        target_ids: set[str] = set()
        for n in graph.by_kind("library"):
            if n.name == name:
                target_ids.add(n.id)
        for n in graph.by_kind("package"):
            if n.name == name:
                target_ids.add(n.id)
        for n in graph.by_kind("external_dep"):
            if n.name == name or n.attrs.get("dotted_name") == name:
                target_ids.add(n.id)
        if not target_ids:
            continue
        for pkg in graph.by_kind("package"):
            for e in graph.out_edges(pkg.id, kind="depends_on"):
                if e.dst_id not in target_ids:
                    continue
                target = graph.node(e.dst_id)
                if target is None:
                    continue
                out.append(
                    ProjectDep(
                        project_name=project_root.name,
                        project_root=str(project_root),
                        package_id=pkg.id,
                        package_name=pkg.name,
                        target_name=target.name,
                        target_kind=target.kind,
                    )
                )
    return sorted(out, key=lambda x: (x.project_name, x.package_name))


def manifest_version_range(
    name: str, base_dir: Path, include_nested: bool = False
) -> VersionRange | None:
    """Across the ecosystem, find every version of a package named *name*.

    Returns ``None`` when no project exposes that name.
    """
    versions: dict[str, list[str]] = {}
    for project_root in _candidates(base_dir, include_nested):
        try:
            graph = session_graph(project_root)
        except Exception:  # pragma: no cover
            continue
        for pkg in list_packages(graph):
            if pkg.name != name:
                continue
            versions.setdefault(pkg.version or "(unspecified)", []).append(
                str(project_root)
            )
    if not versions:
        return None
    sorted_versions = sorted(versions)
    return VersionRange(
        name=name,
        min_version=sorted_versions[0],
        max_version=sorted_versions[-1],
        versions=sorted_versions,
        projects=sorted(
            {p for plist in versions.values() for p in plist},
        ),
    )
