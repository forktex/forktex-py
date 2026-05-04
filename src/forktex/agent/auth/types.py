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

"""Shared types for the unified auth surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

Facet = Literal["cloud", "intelligence", "network"]
AuthKind = Literal["api_key", "jwt", "personal_token"]
Scope = Literal["global", "project"]

FACETS: tuple[Facet, ...] = ("cloud", "intelligence", "network")


@dataclass
class AuthState:
    """Observed state of one facet's credentials on disk.

    ``configured`` is True iff a credential file exists and parses. ``reachable``
    is filled in by the status pinger when ``configured``; left as ``None`` if
    we didn't probe. ``detail`` carries facet-specific key/value extras
    surfaced in ``auth status`` (e.g. intelligence model name, cloud org slug).
    """

    facet: Facet
    configured: bool
    endpoint: Optional[str] = None
    principal: Optional[str] = None
    auth_kind: Optional[AuthKind] = None
    scope: Optional[Scope] = None
    source_path: Optional[Path] = None
    reachable: Optional[bool] = None
    error: Optional[str] = None
    detail: dict[str, str] = field(default_factory=dict)
