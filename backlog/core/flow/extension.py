# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of forktex-core.
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

"""Extension Protocol — the only contract for plugging tenant scope,
RBAC, audit, etc. into ``Flow`` without forking the library.

The library ships THIS file. It does NOT ship concrete extensions.
Every consumer's tenant model is its own (ContextVar +
Member/Permission tables, request-state via FastAPI deps, or
something else entirely); a one-size resolver in core would just
be one product's preferences leaking into all the others.

Each consumer writes a small extension class in its own repo (~20
lines) that wires into its own current-org / current-user accessors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import sqlalchemy as sa
from pydantic import ConfigDict

from forktex_core.types import BaseValueObject, JsonValue

if TYPE_CHECKING:
    # Typing-only, so `extension` stays importable without pulling the engine's
    # module graph in behind it.
    from forktex_core.flow.domain.types import RunInfo


class ColumnDef(BaseValueObject):
    """Declarative spec for an extension-added column on
    ``forktex_flow.run`` or ``forktex_flow.step_run``.

    The library's migration runner ALTERs the target table on init to
    add any declared columns that don't already exist. NULLABLE by
    default; consumers add FK constraints in their own alembic if they
    want strict referential integrity to their own tables.

    Attributes:
        name: column name (snake_case; lowercase letters, digits, underscores).
        type_: SQLAlchemy type — instances or types accepted (e.g.
            ``UUID(as_uuid=True)`` or ``sa.String(64)``).
        nullable: defaults to True. Forcing NOT NULL on existing rows
            requires a backfill the library can't safely automate.
        index: True to create a btree index on the column. Use for
            tenant-scope columns to keep list filters cheap.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    type_: sa.types.TypeEngine | type
    nullable: bool = True
    index: bool = False


@runtime_checkable
class FlowExtension(Protocol):
    """Hooks the library calls at well-defined lifecycle points.

    Every method is optional; returning ``None`` (or omitting the
    method entirely) is a no-op. Use whatever subset fits your
    extension's purpose:

    - ``extra_run_columns`` / ``extra_step_run_columns`` — declare
      additional columns the migration runner adds at startup.
    - ``before_start`` — augment a new run's metadata (inject org_id,
      user_id, trace_id from your app's request context).
    - ``after_complete`` / ``after_fail`` — emit audit events.
    """

    def extra_run_columns(self) -> list[ColumnDef]:
        """Columns added to ``forktex_flow.run`` at init. Default: none."""
        return []

    def extra_step_run_columns(self) -> list[ColumnDef]:
        """Columns added to ``forktex_flow.step_run`` at init. Default: none."""
        return []

    async def before_start(
        self,
        name: str,
        version: int,
        input: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Augment metadata BEFORE the ``run`` row is inserted. Return a
        dict merged into the run's metadata + extension columns. Default:
        returns ``{}`` (no-op).

        Common use: inject ``{"org_id": current_org_id.get()}`` so
        the run is scoped to whatever tenant submitted it.
        """
        return {}

    async def after_complete(self, run: RunInfo, output: JsonValue) -> None:
        """Called after a successful run terminal transition. Default: no-op."""

    async def after_fail(self, run: RunInfo, error: BaseException) -> None:
        """Called after a failed run terminal transition. Default: no-op."""
