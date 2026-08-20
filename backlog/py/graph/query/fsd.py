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

"""FSD-related queries: level, missing atoms, makefile targets."""

from __future__ import annotations

from forktex.graph.models import Graph
from forktex.models.base import ForkTexModel


class FSDStatus(ForkTexModel):
    package_id: str
    package_name: str
    rel_path: str
    fsd_level: str = "L0"
    has_makefile: bool = False
    target_count: int = 0
    available_targets: list[str] = []


def fsd_level_of_package(
    graph: Graph, package_id: str | None = None
) -> list[FSDStatus]:
    """FSD status for one package or every package in the graph.

    ``fsd_level`` reflects the value baked into the package node by
    ``forktex fsd check`` (which writes back to the graph). When the
    project hasn't been checked yet, the field defaults to ``"L0"``.
    """
    pkgs = (
        [graph.node(package_id)] if package_id is not None else graph.by_kind("package")
    )
    out: list[FSDStatus] = []
    for pkg in pkgs:
        if pkg is None or pkg.kind != "package":
            continue
        targets = list(pkg.attrs.get("makefile_targets", []))
        out.append(
            FSDStatus(
                package_id=pkg.id,
                package_name=pkg.name,
                rel_path=pkg.attrs.get("rel_path", ""),
                fsd_level=pkg.attrs.get("fsd_level", "L0"),
                has_makefile=bool(pkg.attrs.get("has_makefile", False)),
                target_count=len(targets),
                available_targets=targets,
            )
        )
    return sorted(out, key=lambda s: s.rel_path)


def packages_below_level(graph: Graph, target: str) -> list[FSDStatus]:
    """Packages whose recorded ``fsd_level`` is below *target* (lex compare).

    Levels are L0 < L1 < L2 < L3 < L4 in the standard. Lex comparison is
    safe up to L9.
    """
    return [s for s in fsd_level_of_package(graph) if s.fsd_level < target]


def makefile_targets_for_package(graph: Graph, package_id: str) -> list[str]:
    """Quick accessor for the cached Makefile target list."""
    pkg = graph.node(package_id)
    if pkg is None or pkg.kind != "package":
        return []
    return list(pkg.attrs.get("makefile_targets", []))
