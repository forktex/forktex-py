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

"""LLM / intelligence automations — a declared SEAM (no model calls yet).

Once the base sync interface is proven, an automation turns natural-language /
image / document context into a *proposed* grid config + rows (applied through
the validated write path), backed by ``forktex-intelligence``. This module
ships only the Protocol + registry today.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Automation(Protocol):
    """Proposes grid config/rows from free-form context (NL, image, doc)."""

    name: str

    async def propose(
        self, *, namespace: str, table_slug: str, context: dict[str, Any]
    ) -> dict[str, Any]: ...


_AUTOMATIONS: dict[str, Automation] = {}


def register_automation(automation: Automation, *, replace: bool = False) -> None:
    if not replace and automation.name in _AUTOMATIONS:
        raise ValueError(f"Automation {automation.name!r} already registered")
    _AUTOMATIONS[automation.name] = automation


def get_automation(name: str) -> Automation | None:
    return _AUTOMATIONS.get(name)


def available_automations() -> list[str]:
    return sorted(_AUTOMATIONS)


__all__ = [
    "Automation",
    "register_automation",
    "get_automation",
    "available_automations",
]
