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

"""Engineering domain models."""

from __future__ import annotations

from pydantic import computed_field

from forktex.models.base import ForkTexModel, Identifiable, Versioned


class TechItem(ForkTexModel):
    """A technology component with name and version."""

    name: str
    version: str = ""
    role: str = ""


class Archetype(Identifiable, Versioned):
    """Technology-generic blueprint for a component type."""

    slug: str
    stack: list[str] = []
    tech_stack: list[TechItem] = []
    features: list[str] = []
    fsd_atoms: list[str] = []
    colors: dict[str, str] = {}

    @computed_field
    @property
    def primary_tech(self) -> str:
        return self.stack[0] if self.stack else ""


class Blueprint(Identifiable, Versioned):
    """Platform-specific development knowledge."""

    slug: str
    platform: str = ""
    archetype: str = ""
    stack: list[str] = []
    engines: list[dict] = []
    routes: list[dict] = []
    models: list[dict] = []
    patterns: list[str] = []


class DeliveryStandard(Identifiable, Versioned):
    """A delivery convention that all platforms follow."""

    slug: str
    path: str = ""
