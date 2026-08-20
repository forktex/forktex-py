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

"""The schema reconciler — declarative apply, in one transaction.

``SchemaReconciler`` is the single core the whole management surface funnels through: hydrate
the actual namespace, merge the caller's (possibly partial) desired schema over it, validate
the result, ``diff`` to an ordered change set, gate destructive changes, then apply the set and
run the physical reconcile tail — all inside one ``atomic`` savepoint so a failure rolls the
whole convergence back. Dispatch is on the change *kind* only; ownership/materialization stay
inside the strategies the primitives and reconcilers already use.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from forktex_core.database.locks import advisory_key, advisory_lock, xact_lock
from forktex_core.grid.domain.enums import IndexState
from forktex_core.grid.domain.schema import Schema
from forktex_core.grid.domain.schema_diff import Change, ChangeOp, ChangeSet, diff
from forktex_core.grid.domain.spec import ColumnSpec, IndexSpec, RelationSpec, TableSpec
from forktex_core.grid.errors import BadRequestError, NotFoundError
from forktex_core.grid.persist import GridIndex, GridRelation, GridTable, reconcile, repos, resolve_schema, schema_repo
from forktex_core.grid.persist.reconcile.concurrent import (
    PhysicalOutcome,
    reconcile_table_indexes_concurrently,
    reconcile_table_promoted_concurrently,
)
from forktex_core.grid.write.tx import atomic
from forktex_core.log import get_logger

logger = get_logger(__name__)


class ReconcileOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    prune: bool = False  # authoritative (drop actual-only) vs partial patch
    allow_destructive: bool = False  # let drops / tightening alters through
    dry_run: bool = False  # plan only, mutate nothing
    concurrently: bool = True
    """Build/drop indexes (and the promoted-column sidecar's unique index) via
    ``CREATE/DROP INDEX CONCURRENTLY`` on a dedicated out-of-band connection,
    instead of inside the same transaction as the rest of the apply.

    This is the safe default: on a populated production table, a transactional
    index build holds a write lock for the build's whole duration. Postgres
    forbids ``CONCURRENTLY`` inside a transaction block, so choosing it means the
    metadata phase commits before the physical phase runs — ``reconcile()`` is no
    longer a single atomic unit end-to-end when this is ``True``. Check
    :attr:`ReconcileReport.physical_complete` rather than assuming success from
    "no exception raised". Set ``False`` only for tests/CI/small or empty
    schemas — never against a populated production table.
    """


class ReconcileReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan: ChangeSet
    applied: tuple[Change, ...] = ()
    resulting: Schema | None = None  # the schema after applying (None on dry-run failures)
    dry_run: bool = False
    concurrently: bool = False
    physical: tuple[PhysicalOutcome, ...] = ()
    """Per-index/sidecar outcome when ``concurrently=True``. Empty when
    ``concurrently=False`` (that path reconciles physically inline; a failure
    there raises instead of being reported)."""
    physical_complete: bool = True
    """``False`` when ``concurrently=True`` and at least one index/sidecar build
    failed. The metadata phase already committed in that case — this is the
    signal a caller must check instead of assuming success from a clean return."""


class SchemaReconciler:
    """Converge a namespace's actual schema toward a desired one."""

    async def plan(self, session: AsyncSession, desired: Schema, *, options: ReconcileOptions) -> ChangeSet:
        """The ordered change set (no mutation). Validates the merged desired state first."""
        actual = await schema_repo.hydrate(session, desired.namespace)
        effective = actual.merged_with(desired, prune=options.prune)
        effective.check()
        return diff(actual, effective, prune=True)

    async def reconcile(
        self, session: AsyncSession, desired: Schema, *, options: ReconcileOptions | None = None
    ) -> ReconcileReport:
        options = options or ReconcileOptions()
        ns = desired.namespace

        if options.dry_run:
            change_set = await self.plan(session, desired, options=options)
            actual = await schema_repo.hydrate(session, ns)
            return ReconcileReport(plan=change_set, resulting=actual, dry_run=True, concurrently=options.concurrently)

        if options.concurrently:
            return await self._reconcile_concurrently(session, ns, desired, options)
        return await self._reconcile_transactional(session, ns, desired, options)

    async def _reconcile_transactional(
        self, session: AsyncSession, ns: str, desired: Schema, options: ReconcileOptions
    ) -> ReconcileReport:
        """``concurrently=False``: one transaction end-to-end, indexes built with a
        write lock. For tests/CI/small schemas, or ``Namespace.batch()`` (which
        forces this to keep its one-transaction promise) — never a populated
        production table.
        """
        # Serialise concurrent applies on this namespace (released at transaction end).
        # The key is derived in Python rather than by Postgres's `hashtext`:
        # `hashtext` is not stable across Postgres majors, so an upgrade would
        # silently re-key every lock and stop serialising what it used to.
        await xact_lock(session, advisory_key("grid.schema.reconcile", ns))

        change_set = await self.plan(session, desired, options=options)
        if change_set.destructive and not options.allow_destructive:
            targets = [c.target for c in change_set.destructive]
            raise BadRequestError(f"refusing {len(targets)} destructive change(s) without allow_destructive: {targets}")

        touched_tables: set[str] = set()
        created_relations: set[str] = set()
        async with atomic(session):
            for change in change_set.changes:
                await self._apply(session, ns, change, touched_tables, created_relations)
            await self._reconcile_physical(session, ns, touched_tables, created_relations)

        resulting = await schema_repo.hydrate(session, ns)
        return ReconcileReport(plan=change_set, applied=change_set.changes, resulting=resulting, concurrently=False)

    async def _reconcile_concurrently(
        self, session: AsyncSession, ns: str, desired: Schema, options: ReconcileOptions
    ) -> ReconcileReport:
        """``concurrently=True`` (the default): metadata commits before indexes and
        the promoted-column sidecar are built, on a dedicated AUTOCOMMIT connection
        outside the transaction that committed the metadata — see
        :attr:`ReconcileOptions.concurrently` for why this can't be one transaction.

        Held for the whole call: a **session-scoped** advisory lock (not the
        transaction-scoped one the other path uses — that would release at the
        metadata commit, before the physical phase even starts) on a dedicated
        connection, reused as the AUTOCOMMIT connection for phase 2 so the extra
        connection cost is exactly one, not two.
        """
        # `session.get_bind()` returns the underlying *sync* Engine (the ORM always
        # deals in sync engines/connections, wrapped for async via greenlet) — not
        # the `AsyncEngine` that `advisory_lock`/`engine.connect()` need. Re-wrapping
        # it is the documented pattern: `AsyncEngine(sync_engine)` is a thin proxy
        # over the same connection pool, not a second pool.
        bind = session.get_bind()
        assert isinstance(bind, sa.Engine), "grid sessions are always bound to an Engine, never a raw Connection"
        engine = AsyncEngine(bind)
        lock_key = advisory_key("grid.schema.reconcile", ns)
        schema = resolve_schema(session)

        async with advisory_lock(engine, lock_key) as lock_conn:
            change_set = await self.plan(session, desired, options=options)
            if change_set.destructive and not options.allow_destructive:
                targets = [c.target for c in change_set.destructive]
                raise BadRequestError(
                    f"refusing {len(targets)} destructive change(s) without allow_destructive: {targets}"
                )

            touched_tables: set[str] = set()
            created_relations: set[str] = set()
            async with atomic(session):
                for change in change_set.changes:
                    await self._apply(session, ns, change, touched_tables, created_relations)
                # Relation-cardinality indexes stay transactional even here: they are
                # only ever built for a namespace's *new* relations (empty grid_edge
                # rows), so there is nothing populated to hold a lock against.
                await self._reconcile_relations_physical(session, ns, created_relations)
            await session.commit()  # phase 1 durable before the out-of-band phase runs

            # A table whose declared index is still `invalid` from a previous
            # failed build has no metadata change to surface it via `touched_tables`
            # this time — without this, "reapply to recover" would silently do
            # nothing for it. `GridIndex.state` is the only physical outcome that
            # persists across calls (the implicit per-column-unique index has no
            # durable health tracking of its own; recovering one of those needs a
            # metadata change too, e.g. toggling `is_unique` off then on).
            invalid_index_tables = await session.scalars(
                sa.select(GridTable.slug)
                .join(GridIndex, GridIndex.table_id == GridTable.id)
                .where(
                    GridTable.namespace == ns,
                    GridTable.archived_at.is_(None),
                    GridIndex.archived_at.is_(None),
                    GridIndex.state == IndexState.invalid,
                )
                .distinct()
            )
            touched_tables |= set(invalid_index_tables)

            lock_conn = await lock_conn.execution_options(isolation_level="AUTOCOMMIT")
            physical: list[PhysicalOutcome] = []
            for slug in sorted(touched_tables):
                if await self._tid(session, slug, ns) is None:
                    continue  # the table was dropped in this batch
                ref = await repos.load_table(session, slug, ns)
                orm = await session.get(GridTable, ref.id)
                assert orm is not None  # a live TableRef always has its row
                physical.extend(
                    await reconcile_table_indexes_concurrently(lock_conn, session, table=orm, schema=schema)
                )
                physical.extend(
                    await reconcile_table_promoted_concurrently(lock_conn, session, table=orm, schema=schema)
                )

            resulting = await schema_repo.hydrate(session, ns)
            physical_complete = all(o.state == "live" for o in physical)
            if not physical_complete:
                failed = [o.index_name for o in physical if o.state != "live"]
                logger.warning(
                    "grid: reconcile committed metadata but %d physical structure(s) failed: %s",
                    len(failed),
                    failed,
                )
            return ReconcileReport(
                plan=change_set,
                applied=change_set.changes,
                resulting=resulting,
                concurrently=True,
                physical=tuple(physical),
                physical_complete=physical_complete,
            )

    async def _apply(
        self,
        session: AsyncSession,
        ns: str,
        change: Change,
        touched_tables: set[str],
        created_relations: set[str],
    ) -> None:
        op, spec = change.op, change.desired
        match op:
            case ChangeOp.create_table:
                assert isinstance(spec, TableSpec)
                await repos.create_table(session, spec.model_copy(update={"namespace": ns}))
                touched_tables.add(change.key)
            case ChangeOp.alter_table:
                assert isinstance(spec, TableSpec)
                await schema_repo.alter_table(session, spec=spec.model_copy(update={"namespace": ns}), namespace=ns)
            case ChangeOp.drop_table:
                await schema_repo.archive_table(session, slug=change.key, namespace=ns)
            case ChangeOp.add_column:
                assert isinstance(spec, ColumnSpec) and change.table is not None
                ref = await repos.load_table(session, change.table, ns)
                await repos.add_column(session, ref, spec)
                touched_tables.add(change.table)
            case ChangeOp.alter_column:
                assert isinstance(spec, ColumnSpec) and change.table is not None
                await schema_repo.alter_column(
                    session, table_id=await self._require_tid(session, change.table, ns), spec=spec
                )
                touched_tables.add(change.table)
            case ChangeOp.drop_column:
                assert change.table is not None
                await schema_repo.archive_column(
                    session, table_id=await self._require_tid(session, change.table, ns), key=change.key
                )
                touched_tables.add(change.table)
            case ChangeOp.create_relation:
                assert isinstance(spec, RelationSpec)
                await repos.create_relation(session, spec, namespace=ns)
                created_relations.add(change.key)
            case ChangeOp.alter_relation:
                assert isinstance(spec, RelationSpec)
                await schema_repo.alter_relation(session, spec=spec, namespace=ns)
            case ChangeOp.drop_relation:
                await schema_repo.archive_relation(session, key=change.key, namespace=ns)
            case ChangeOp.create_index:
                assert isinstance(spec, IndexSpec) and change.table is not None
                await schema_repo.create_index(
                    session, table_id=await self._require_tid(session, change.table, ns), spec=spec, namespace=ns
                )
                touched_tables.add(change.table)
            case ChangeOp.drop_index:
                assert isinstance(change.actual, IndexSpec) and change.table is not None
                await schema_repo.archive_index(
                    session, table_id=await self._require_tid(session, change.table, ns), spec=change.actual
                )
                touched_tables.add(change.table)

    async def _reconcile_physical(
        self, session: AsyncSession, ns: str, touched_tables: set[str], created_relations: set[str]
    ) -> None:
        """Materialise physical structures for every touched (still-live) table + new relation."""
        for slug in sorted(touched_tables):
            if await self._tid(session, slug, ns) is None:
                continue  # the table was dropped in this batch
            ref = await repos.load_table(session, slug, ns)
            await reconcile.reconcile_table(session, ref)
        await self._reconcile_relations_physical(session, ns, created_relations)

    async def _reconcile_relations_physical(self, session: AsyncSession, ns: str, created_relations: set[str]) -> None:
        """Materialise cardinality indexes for every newly-created relation.

        Always transactional, regardless of ``concurrently``: a relation just
        created in this same call has no ``grid_edge`` rows yet, so there is
        nothing populated to hold a lock against.
        """
        for key in sorted(created_relations):
            relation = await session.scalar(
                sa.select(GridRelation).where(
                    GridRelation.key == key, GridRelation.namespace == ns, GridRelation.archived_at.is_(None)
                )
            )
            if relation is not None:
                await reconcile.reconcile_relation(session, relation)

    async def _tid(self, session: AsyncSession, slug: str, ns: str) -> uuid.UUID | None:
        return await session.scalar(
            sa.select(GridTable.id).where(
                GridTable.slug == slug, GridTable.namespace == ns, GridTable.archived_at.is_(None)
            )
        )

    async def _require_tid(self, session: AsyncSession, slug: str, ns: str) -> uuid.UUID:
        tid = await self._tid(session, slug, ns)
        if tid is None:
            raise NotFoundError(f"table '{slug}' not found in namespace {ns!r}")
        return tid


__all__ = ["ReconcileOptions", "ReconcileReport", "SchemaReconciler"]
