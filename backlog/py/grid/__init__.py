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

"""forktex.grid — a self-describing HTTP interface over ``forktex_core[grid]``.

This is forktex-py's purpose as the most generic consumer of the grid: it
exposes the grid's *interaction state space* (the type registry + per-table
schema + capability descriptors) and a constrained dynamic config/CRUD/query
surface, so a generic JSX studio can render and drive any tenant-defined
schema with no per-entity code.

The HTTP/DTO interface lives here (not in core — core stays consumer-agnostic).
File-format adapters (``forktex.grid.adapters``) and LLM automations
(``forktex.grid.automations``) are declared seams, filled once the base sync
interface is proven.

``build_app`` lives in :mod:`forktex.grid.app`; it is not imported here so the
package (and the ``grid`` CLI group) stays importable without the ``[api]``
extra — only ``forktex grid serve`` actually needs FastAPI + forktex_core[grid].
"""

__all__: list[str] = []
