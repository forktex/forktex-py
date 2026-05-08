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

"""Dependency-graph queries (depends_on, imports)."""

from __future__ import annotations

from forktex.graph.models import Graph
from forktex.graph.query.models import PackageSummary
from forktex.graph.query.project import list_packages
from forktex.models.base import ForkTexModel


class LibrarySummary(ForkTexModel):
    id: str
    name: str
    version_constraint: str = ""


class ImportEdge(ForkTexModel):
    src_module_id: str
    src_module: str = ""
    target_id: str
    target_name: str = ""
    target_kind: str  # "module" | "package" | "library" | "external_dep"


# ── library queries ──────────────────────────────────────────────────────


def list_libraries_for_package(graph: Graph, package_id: str) -> list[LibrarySummary]:
    """Libraries this package declares as deps in pyproject.toml."""
    pkg = graph.node(package_id)
    if pkg is None or pkg.kind != "package":
        return []
    out: list[LibrarySummary] = []
    for e in graph.out_edges(pkg.id, kind="depends_on"):
        lib = graph.node(e.dst_id)
        if lib is None or lib.kind != "library":
            continue
        out.append(
            LibrarySummary(
                id=lib.id,
                name=lib.name,
                version_constraint=lib.attrs.get("version_constraint", ""),
            )
        )
    return sorted(out, key=lambda x: x.name)


def packages_depending_on(graph: Graph, name: str) -> list[PackageSummary]:
    """Packages that declare *name* (a library or sibling package) as a dep.

    Matches by node name (libraries are stored by their PyPI name).
    """
    target_ids = {n.id for n in graph.by_kind("library") if n.name == name}
    target_ids.update(p.id for p in graph.by_kind("package") if p.name == name)
    if not target_ids:
        return []
    pkg_ids: set[str] = set()
    for tid in target_ids:
        for e in graph.in_edges(tid, kind="depends_on"):
            src = graph.node(e.src_id)
            if src and src.kind == "package":
                pkg_ids.add(src.id)
    summaries = {p.id: p for p in list_packages(graph)}
    return [summaries[pid] for pid in sorted(pkg_ids) if pid in summaries]


# ── imports queries ──────────────────────────────────────────────────────


def imports_of_module(graph: Graph, module_id: str) -> list[ImportEdge]:
    """Every ``imports`` edge originating from *module_id*."""
    src_node = graph.node(module_id)
    if src_node is None or src_node.kind != "module":
        return []
    out: list[ImportEdge] = []
    for e in graph.out_edges(src_node.id, kind="imports"):
        target = graph.node(e.dst_id)
        if target is None:
            continue
        out.append(
            ImportEdge(
                src_module_id=src_node.id,
                src_module=src_node.attrs.get(
                    "dotted_name", src_node.attrs.get("rel_path", src_node.name)
                ),
                target_id=target.id,
                target_name=target.attrs.get("dotted_name", target.name),
                target_kind=target.kind,
            )
        )
    return sorted(out, key=lambda x: (x.target_kind, x.target_name))


def importers_of(graph: Graph, target: str) -> list[ImportEdge]:
    """Modules that import *target* (matching by dotted name OR node name).

    *target* may be a library (e.g. ``"httpx"``), a sibling package, or an
    in-project module dotted name (e.g. ``"forktex.graph.io_proxy"``).
    """
    target_ids: set[str] = set()
    for kind in ("library", "package", "module", "external_dep"):
        for n in graph.by_kind(kind):
            dotted = n.attrs.get("dotted_name", "")
            if n.name == target or dotted == target:
                target_ids.add(n.id)
    out: list[ImportEdge] = []
    for tid in target_ids:
        target_node = graph.node(tid)
        if target_node is None:
            continue
        for e in graph.in_edges(tid, kind="imports"):
            src_node = graph.node(e.src_id)
            if src_node is None or src_node.kind != "module":
                continue
            out.append(
                ImportEdge(
                    src_module_id=src_node.id,
                    src_module=src_node.attrs.get(
                        "dotted_name", src_node.attrs.get("rel_path", src_node.name)
                    ),
                    target_id=target_node.id,
                    target_name=target_node.attrs.get("dotted_name", target_node.name),
                    target_kind=target_node.kind,
                )
            )
    return sorted(out, key=lambda x: x.src_module)
