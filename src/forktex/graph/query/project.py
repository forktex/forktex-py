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

"""Per-project graph queries: packages, domains, modules."""

from __future__ import annotations

import fnmatch

from forktex.graph.models import Graph
from forktex.graph.query._walk import first_parent_of_kind, neighbors_of_kind
from forktex.graph.query.models import (
    DomainSummary,
    ModuleSummary,
    PackageSummary,
    ProjectMetadata,
)


def get_project_metadata(graph: Graph) -> ProjectMetadata:
    """Top-level facts about the project graph."""
    project_roots = graph.by_kind("project_root")
    name = project_roots[0].name if project_roots else "project"
    root = (
        project_roots[0].attrs.get("abs_path", "") if project_roots else graph.meta.root
    )
    packages = graph.by_kind("package")
    fsd_level = "L0"
    has_makefile = False
    if packages:
        # Pick the root-most package's level (rel_path == "."), else any.
        root_pkg = next(
            (p for p in packages if p.attrs.get("rel_path") in {".", ""}), packages[0]
        )
        fsd_level = root_pkg.attrs.get("fsd_level", "L0")
        has_makefile = bool(root_pkg.attrs.get("has_makefile", False))
    return ProjectMetadata(
        name=name,
        root=root,
        package_count=len(packages),
        domain_count=len(graph.by_kind("domain")),
        module_count=len(graph.by_kind("module")),
        library_count=len(graph.by_kind("library")),
        fsd_level=fsd_level,
        has_makefile=has_makefile,
    )


def list_packages(graph: Graph) -> list[PackageSummary]:
    """Every package in the project, sorted by rel_path."""
    out: list[PackageSummary] = []
    for pkg in sorted(
        graph.by_kind("package"), key=lambda n: n.attrs.get("rel_path", "")
    ):
        domains = neighbors_of_kind(
            graph, pkg.id, edge_kind="contains", neighbor_kind="domain"
        )
        module_count = sum(
            len(
                neighbors_of_kind(
                    graph, d.id, edge_kind="contains", neighbor_kind="module"
                )
            )
            for d in domains
        )
        out.append(
            PackageSummary(
                id=pkg.id,
                name=pkg.name,
                rel_path=pkg.attrs.get("rel_path", "."),
                version=pkg.attrs.get("version", ""),
                language=pkg.attrs.get("language", "python"),
                publishable=bool(pkg.attrs.get("publishable", True)),
                has_makefile=bool(pkg.attrs.get("has_makefile", False)),
                fsd_level=pkg.attrs.get("fsd_level", "L0"),
                domain_count=len(domains),
                module_count=module_count,
            )
        )
    return out


def find_package_by_path(graph: Graph, rel_path: str) -> PackageSummary | None:
    """Locate the package whose rel_path is the longest prefix of *rel_path*.

    Useful for "where does this file live in the project's package tree?".
    Returns ``None`` when no package contains the path.
    """
    rel = rel_path.replace("\\", "/").lstrip("/")
    pkgs = list_packages(graph)
    best: PackageSummary | None = None
    best_len = -1
    for p in pkgs:
        prefix = (p.rel_path.rstrip("/") + "/") if p.rel_path != "." else ""
        if p.rel_path == ".":
            if best_len < 0:
                best, best_len = p, 0
        elif rel == p.rel_path or rel.startswith(prefix):
            if len(p.rel_path) > best_len:
                best, best_len = p, len(p.rel_path)
    return best


def list_domains(graph: Graph, package_id: str | None = None) -> list[DomainSummary]:
    """Domains in one package (when ``package_id`` is given) or every package."""
    domains: list[DomainSummary] = []
    pkgs = (
        [graph.node(package_id)] if package_id is not None else graph.by_kind("package")
    )
    for pkg in pkgs:
        if pkg is None or pkg.kind != "package":
            continue
        for n in neighbors_of_kind(
            graph, pkg.id, edge_kind="contains", neighbor_kind="domain"
        ):
            modules = neighbors_of_kind(
                graph, n.id, edge_kind="contains", neighbor_kind="module"
            )
            domains.append(
                DomainSummary(
                    id=n.id,
                    name=n.name,
                    rel_path=n.attrs.get("rel_path", ""),
                    package_id=pkg.id,
                    module_count=len(modules),
                )
            )
    return sorted(domains, key=lambda d: d.rel_path)


def list_modules_in_domain(graph: Graph, domain_id: str) -> list[ModuleSummary]:
    """Top-level modules under *domain_id* in stable rel_path order."""
    domain = graph.node(domain_id)
    if domain is None or domain.kind != "domain":
        return []
    parent = first_parent_of_kind(
        graph, domain.id, edge_kind="contains", parent_kind="package"
    )
    package_id = parent.id if parent else ""
    out: list[ModuleSummary] = []
    for m in neighbors_of_kind(
        graph, domain.id, edge_kind="contains", neighbor_kind="module"
    ):
        out.append(
            ModuleSummary(
                id=m.id,
                name=m.name,
                rel_path=m.attrs.get("rel_path", ""),
                domain_id=domain.id,
                package_id=package_id,
                dotted_name=m.attrs.get("dotted_name", ""),
            )
        )
    return sorted(out, key=lambda x: x.rel_path)


def find_modules(graph: Graph, name_pattern: str) -> list[ModuleSummary]:
    """Search modules by glob over their bare name OR their dotted name.

    ``name_pattern`` uses fnmatch semantics (``*build*``, ``test_*``).
    Matches against module ``name`` and ``dotted_name``.
    """
    matches: list[ModuleSummary] = []
    for m in graph.by_kind("module"):
        dotted = m.attrs.get("dotted_name", "")
        if not (
            fnmatch.fnmatchcase(m.name, name_pattern)
            or (dotted and fnmatch.fnmatchcase(dotted, name_pattern))
        ):
            continue
        # Resolve domain + package.
        domain_id = ""
        package_id = ""
        for e in graph.in_edges(m.id, kind="contains"):
            parent = graph.node(e.src_id)
            if parent and parent.kind == "domain":
                domain_id = parent.id
                for ee in graph.in_edges(parent.id, kind="contains"):
                    pp = graph.node(ee.src_id)
                    if pp and pp.kind == "package":
                        package_id = pp.id
                        break
                break
        matches.append(
            ModuleSummary(
                id=m.id,
                name=m.name,
                rel_path=m.attrs.get("rel_path", ""),
                domain_id=domain_id,
                package_id=package_id,
                dotted_name=dotted,
            )
        )
    return sorted(matches, key=lambda x: x.rel_path)
