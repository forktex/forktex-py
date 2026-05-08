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

"""Lightweight Pydantic models for query results — JSON-friendly and
human-friendly when echoed back to the LLM."""

from __future__ import annotations

from forktex.models.base import ForkTexModel


class ProjectMetadata(ForkTexModel):
    """Top-level project facts derived from the graph + root manifest."""

    name: str
    root: str
    package_count: int
    domain_count: int
    module_count: int
    library_count: int
    fsd_level: str = "L0"
    has_makefile: bool = False


class PackageSummary(ForkTexModel):
    id: str
    name: str
    rel_path: str
    version: str = ""
    language: str = "python"
    publishable: bool = True
    has_makefile: bool = False
    fsd_level: str = "L0"
    domain_count: int = 0
    module_count: int = 0


class DomainSummary(ForkTexModel):
    id: str
    name: str
    rel_path: str
    package_id: str
    module_count: int = 0


class ModuleSummary(ForkTexModel):
    id: str
    name: str
    rel_path: str
    domain_id: str
    package_id: str
    dotted_name: str = ""
