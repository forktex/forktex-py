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

"""Project graph → C4 :class:`Workspace` projection.

The C4 view treats the project root as a Workspace, each package as a
SoftwareSystem, each domain as a Container, and each module as a Component.
For the OS scope, every registered project becomes a SoftwareSystem and
the global ``.forktex`` itself is a Container holding registry files.
"""

from __future__ import annotations

import re

from forktex.architecture.models import (
    Component,
    Container,
    ServiceType,
    SoftwareSystem,
    Workspace,
)
from forktex.graph.models import Graph, GraphNode


_ID_RE = re.compile(r"[^A-Za-z0-9_]")


def _safe_id(s: str) -> str:
    cleaned = _ID_RE.sub("_", s)
    if cleaned and cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned or "id"


def _module_to_component(node: GraphNode) -> Component:
    rel = node.attrs.get("rel_path", node.name)
    return Component(
        id=_safe_id(node.id),
        name=node.name,
        description=rel,
        files=[rel],
    )


def _domain_to_container(graph: Graph, node: GraphNode) -> Container:
    components = [
        _module_to_component(m)
        for m in graph.neighbors(node.id, kind="contains")
        if m.kind == "module"
    ]
    return Container(
        id=_safe_id(node.id),
        name=node.name,
        description=node.attrs.get("rel_path", node.name),
        service_type=ServiceType.COMPUTE,
        components=components,
    )


def _package_to_system(graph: Graph, node: GraphNode) -> SoftwareSystem:
    containers: list[Container] = []
    domains_seen = set()
    for child in graph.neighbors(node.id, kind="contains"):
        if child.kind == "domain" and child.id not in domains_seen:
            domains_seen.add(child.id)
            containers.append(_domain_to_container(graph, child))
    return SoftwareSystem(
        id=_safe_id(node.id),
        name=node.name,
        description=node.attrs.get("rel_path", ""),
        containers=containers,
        domains=[c.name for c in containers],
        fsd_level=node.attrs.get("fsd_level", "L0"),
    )


def _project_workspace(graph: Graph) -> Workspace:
    project_roots = graph.by_kind("project_root")
    name = project_roots[0].name if project_roots else "project"
    systems = [_package_to_system(graph, p) for p in graph.by_kind("package")]
    return Workspace(
        id=_safe_id(name),
        name=name,
        description="ForkTex project graph (C4 projection)",
        systems=systems,
    )


def _os_workspace(graph: Graph) -> Workspace:
    systems: list[SoftwareSystem] = []
    for proj in graph.by_kind("registered_project"):
        files = [
            Component(
                id=_safe_id(f"{proj.id}::{f.name}"),
                name=f.name,
                description=f.attrs.get("rel_path", f.name),
                files=[f.attrs.get("rel_path", f.name)],
            )
            for f in graph.neighbors(proj.id, kind="writes_to")
            if f.kind == "file"
        ]
        systems.append(
            SoftwareSystem(
                id=_safe_id(proj.id),
                name=proj.name,
                description=proj.attrs.get("abs_path", ""),
                containers=[
                    Container(
                        id=_safe_id(f"{proj.id}__forktex_dir"),
                        name=".forktex",
                        description="Local .forktex directory",
                        service_type=ServiceType.COMPUTE,
                        components=files,
                    )
                ],
            )
        )
    return Workspace(
        id="forktex_host",
        name="ForkTex Host",
        description="Host-wide footprint of registered ForkTex projects",
        systems=systems,
    )


def graph_to_workspace(graph: Graph) -> Workspace:
    """Project a typed graph onto the C4 :class:`Workspace` model."""
    if graph.meta.scope == "os":
        return _os_workspace(graph)
    return _project_workspace(graph)
