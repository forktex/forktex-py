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

"""Base models shared across the entire ForkTex model graph."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ForkTexModel(BaseModel):
    """Root base for all ForkTex models.

    - extra="allow" so forward-compatible fields don't break deserialization
    - populate_by_name=True so both alias and field name work
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Identifiable(ForkTexModel):
    """Any model with id + name + description."""

    id: str
    name: str
    description: str = ""


class Versioned(ForkTexModel):
    """Any model with version tracking."""

    version: str = "1.0.0"
    status: Literal["draft", "active", "deprecated", "planning"] = "active"
    updated_at: datetime | None = None


class Tagged(ForkTexModel):
    """Any model with free-form tags."""

    tags: list[str] = []
