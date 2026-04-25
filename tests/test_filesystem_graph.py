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

from forktex.core.paths import require_project_root
from forktex.filesystem.graph import build_project_graph


def test_build_project_graph_detects_root_packages_and_child_manifests():
    project_root = require_project_root(__file__)

    graph = build_project_graph(project_root)

    package_names = {pkg.name for pkg in graph.packages}
    assert "forktex" in package_names

    # forktex-py is now a single-package repo. The four ecosystem SDKs
    # (forktex-intelligence, forktex-cloud, forktex-core, forktex-documents)
    # live in their own repos and are consumed as ordinary dependencies.
    child_manifest_paths = {
        p.relative_to(project_root).as_posix() for p in graph.child_manifest_paths
    }
    assert child_manifest_paths == set() or all(
        not p.startswith(
            (
                "forktex-core/",
                "forktex-documents/",
                "forktex-intelligence/",
                "forktex-cloud/",
            )
        )
        for p in child_manifest_paths
    )


def test_build_project_graph_detects_main_forktex_domains():
    project_root = require_project_root(__file__)

    graph = build_project_graph(project_root)

    domain_names = {domain.name for domain in graph.domains}
    assert "fsd" in domain_names
    assert "architecture" in domain_names
    assert "manifest" in domain_names
    assert "agent" in domain_names
