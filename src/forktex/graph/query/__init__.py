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

"""Engineering-aware query layer over the source-of-truth graph.

Pure-Python primitives that turn ``forktex.graph.Graph`` into a queryable
knowledge base. The agentic CLI wraps these as tools in
``forktex.agent.tools.graph_tools``; humans can use them directly from
the Python REPL or the ``forktex graph ask`` family of CLI commands.

All primitives return Pydantic models or simple data structures so the
results JSON-encode cleanly for LLM tool calls.
"""

from __future__ import annotations

from forktex.graph.query.cache import bust as bust_cache
from forktex.graph.query.cache import session_graph
from forktex.graph.query.deps import (
    ImportEdge,
    LibrarySummary,
    importers_of,
    imports_of_module,
    list_libraries_for_package,
    packages_depending_on,
)
from forktex.graph.query.ecosystem import (
    EcosystemRow,
    ProjectDep,
    VersionRange,
    ecosystem_fsd_matrix,
    manifest_version_range,
    reverse_dependents,
)
from forktex.graph.query.fsd import (
    FSDStatus,
    fsd_level_of_package,
    makefile_targets_for_package,
    packages_below_level,
)
from forktex.graph.query.models import (
    DomainSummary,
    ModuleSummary,
    PackageSummary,
    ProjectMetadata,
)
from forktex.graph.query.project import (
    find_modules,
    find_package_by_path,
    get_project_metadata,
    list_domains,
    list_modules_in_domain,
    list_packages,
)
from forktex.graph.query.structure import (
    StructureMatch,
    Touch,
    files_touched_recently,
    validate_path,
    writers_for_path,
)


__all__ = [
    # Models
    "DomainSummary",
    "EcosystemRow",
    "FSDStatus",
    "ImportEdge",
    "LibrarySummary",
    "ModuleSummary",
    "PackageSummary",
    "ProjectDep",
    "ProjectMetadata",
    "StructureMatch",
    "Touch",
    "VersionRange",
    # Cache
    "bust_cache",
    "session_graph",
    # Project
    "find_modules",
    "find_package_by_path",
    "get_project_metadata",
    "list_domains",
    "list_modules_in_domain",
    "list_packages",
    # Deps
    "importers_of",
    "imports_of_module",
    "list_libraries_for_package",
    "packages_depending_on",
    # FSD
    "fsd_level_of_package",
    "makefile_targets_for_package",
    "packages_below_level",
    # Structure
    "files_touched_recently",
    "validate_path",
    "writers_for_path",
    # Ecosystem
    "ecosystem_fsd_matrix",
    "manifest_version_range",
    "reverse_dependents",
]
