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

"""``sync_promoted`` upserts the whole batch in one statement, not one per row.

`create_many` on a table with a promoted column used to cost N sequential round
trips for N rows — the per-write dual-write path, separate from (and in addition
to) the one-time backfill `reconcile_table_promoted` runs when a column is first
promoted. This pins the fix: one INSERT against the sidecar table, whatever the
batch size.
"""

from __future__ import annotations

import sqlalchemy as sa

from forktex_core.grid import ColumnSpec, Namespace, Schema, TableSpec
from forktex_core.grid.domain.enums import Materialization

NS = "sync-promoted-batching"


async def test_create_many_issues_one_sidecar_statement_for_the_whole_batch(session) -> None:
    ns = Namespace(session, NS)
    await ns.apply(
        Schema(
            tables={
                "people": TableSpec(
                    slug="people",
                    label="People",
                    namespace=NS,
                    columns=(
                        ColumnSpec(key="name", label="Name", type_id="text"),
                        ColumnSpec(key="age", label="Age", type_id="integer", materialization=Materialization.promoted),
                    ),
                )
            }
        )
    )
    await session.commit()

    people = await ns.table("people")

    sidecar_statements: list[str] = []

    def _capture(_conn, _cursor, statement, *_args, **_kwargs):
        if "grid_promoted_" in statement and "insert" in statement.lower():
            sidecar_statements.append(statement)

    engine = session.get_bind()
    sa.event.listen(engine, "before_cursor_execute", _capture)
    try:
        await people.create_many([{"name": f"person-{i}", "age": i} for i in range(25)])
    finally:
        sa.event.remove(engine, "before_cursor_execute", _capture)

    assert len(sidecar_statements) == 1, (
        f"expected exactly one sidecar INSERT for the whole batch, got {len(sidecar_statements)}"
    )
