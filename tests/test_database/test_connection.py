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


from __future__ import annotations

from collections.abc import AsyncIterator
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.exc import PendingRollbackError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from forktex.database import (
    BaseDBModel,
    Database,
    DatabaseNotInitializedError,
    TimestampMixin,
    TransactionBoundaryError,
    close_engine,
    get_engine,
    init_engine,
    require_default,
    savepoint,
    session,
    transaction,
)
from tests.conftest import sessions_for


class _ConnTestWidget(BaseDBModel, TimestampMixin):
    __tablename__ = "conn_test_widget"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100))


class _ConnTestUnique(BaseDBModel):
    __tablename__ = "conn_test_unique"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(sa.String(50), unique=True)


@pytest_asyncio.fixture
async def engine_and_session(postgres_url_str: str, fresh_schema: str) -> AsyncIterator[None]:
    await init_engine(postgres_url_str, schema_translate_map={None: fresh_schema})
    raw_engine = get_engine()
    async with raw_engine.begin() as conn:
        await conn.run_sync(BaseDBModel.metadata.create_all)
    yield
    await close_engine()


@pytest.mark.asyncio
async def test_a_transaction_commits_on_success(engine_and_session: None) -> None:
    async with transaction() as session:
        session.add(_ConnTestWidget(name="alpha"))
    async with transaction() as session:
        result = await session.execute(sa.select(_ConnTestWidget).where(_ConnTestWidget.name == "alpha"))
        assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_a_transaction_rolls_back_on_error(engine_and_session: None) -> None:
    with pytest.raises(ValueError):
        async with transaction() as session:
            session.add(_ConnTestWidget(name="beta"))
            raise ValueError("intentional rollback")
    async with transaction() as session:
        result = await session.execute(sa.select(_ConnTestWidget).where(_ConnTestWidget.name == "beta"))
        assert result.scalar_one_or_none() is None


def _checked_out_connections() -> int:
    return get_engine().pool.checkedout()


@pytest.mark.asyncio
async def test_a_transaction_returns_its_connection_as_soon_as_the_block_raises(
    engine_and_session: None,
) -> None:
    with pytest.raises(ValueError):
        async with transaction() as session:
            session.add(_ConnTestWidget(name="raised"))
            await session.flush()
            raise ValueError("boom")
    assert _checked_out_connections() == 0


@pytest.mark.asyncio
async def test_the_dependency_rolls_back_when_the_route_raises(engine_and_session: None) -> None:
    dependency = transaction.dependency()
    session = await anext(dependency)
    session.add(_ConnTestWidget(name="raised"))
    await session.flush()
    with pytest.raises(ValueError):
        await dependency.athrow(ValueError("route failed"))
    assert _checked_out_connections() == 0
    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_a_savepoint_releases_into_its_enclosing_transaction(engine_and_session: None) -> None:
    async with session() as owner:
        async with savepoint(owner):
            owner.add(_ConnTestWidget(name="pending"))
        assert owner.in_transaction()
        await owner.rollback()
    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_an_owned_session_refuses_the_boundary_calls_it_does_not_own(engine_and_session: None) -> None:
    for call in ("commit", "rollback"):
        with pytest.raises(TransactionBoundaryError, match=call):
            async with transaction() as session:
                await getattr(session, call)()
    with pytest.raises(TransactionBoundaryError, match="begin"):
        async with transaction() as session:
            session.begin()


@pytest.mark.asyncio
async def test_a_midway_commit_cannot_half_apply_a_unit_of_work(engine_and_session: None) -> None:
    with pytest.raises(TransactionBoundaryError):
        async with transaction() as session:
            session.add(_ConnTestWidget(name="early"))
            await session.commit()
            session.add(_ConnTestWidget(name="late"))
    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_a_plain_session_owns_its_own_boundary(engine_and_session: None) -> None:
    async with session() as plain:
        plain.add(_ConnTestWidget(name="kept"))
        await plain.commit()
        plain.add(_ConnTestWidget(name="dropped"))
        await plain.rollback()
    assert await _widget_names() == {"kept"}


@pytest.mark.asyncio
async def test_a_transaction_before_init_engine_raises() -> None:
    await close_engine()
    with pytest.raises(DatabaseNotInitializedError, match="not initialized"):
        async with transaction():
            pass


async def _widget_names() -> set[str]:
    async with transaction() as session:
        return set((await session.execute(sa.select(_ConnTestWidget.name))).scalars())


@transaction
async def _add_widget(session: AsyncSession, name: str) -> None:
    session.add(_ConnTestWidget(name=name))
    await session.flush()


@pytest.mark.asyncio
async def test_transactional_without_a_session_owns_and_commits_one(engine_and_session: None) -> None:
    await _add_widget(name="owned")
    assert await _widget_names() == {"owned"}


@pytest.mark.asyncio
async def test_transactional_without_a_session_rolls_back_on_raise(engine_and_session: None) -> None:
    @transaction
    async def add_then_fail(session: AsyncSession) -> None:
        session.add(_ConnTestWidget(name="lost"))
        await session.flush()
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await add_then_fail()
    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_transactional_owned_session_refuses_its_own_transaction_block(engine_and_session: None) -> None:

    @transaction
    async def add_in_explicit_block(session: AsyncSession) -> None:
        async with session.begin():
            await _add_widget(session=session, name="explicit")

    with pytest.raises(TransactionBoundaryError, match="begin"):
        await add_in_explicit_block()
    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_transactional_a_b_c_rolls_back_together(engine_and_session: None) -> None:
    with pytest.raises(RuntimeError, match="c failed"):
        async with transaction() as session:
            await _add_widget(session, "b")
            session.add(_ConnTestWidget(name="a"))
            raise RuntimeError("c failed")
    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_transactional_never_commits_a_session_it_was_handed(engine_and_session: None) -> None:
    async with session() as plain:
        assert not plain.in_transaction()
        await _add_widget(plain, "b")
        await plain.rollback()
    assert await _widget_names() == set()

    async with session() as plain:
        await _add_widget(plain, "b")
        await plain.commit()
    assert await _widget_names() == {"b"}


@transaction
async def _add_widget_then_fail(session: AsyncSession, *, name: str) -> None:
    session.add(_ConnTestWidget(name=name))
    await session.flush()
    raise ValueError("callee failed")


@pytest.mark.asyncio
async def test_transactional_handed_a_session_joins_it_rather_than_nesting(
    engine_and_session: None,
) -> None:
    with pytest.raises(ValueError, match="callee failed"):
        async with transaction() as session:
            session.add(_ConnTestWidget(name="caller"))
            await _add_widget_then_fail(session, name="callee")
    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_a_caller_may_isolate_a_part_that_is_allowed_to_fail(
    engine_and_session: None,
) -> None:
    async with transaction() as session:
        session.add(_ConnTestWidget(name="batch-survives"))
        with pytest.raises(ValueError, match="callee failed"):
            async with savepoint(session):
                await _add_widget_then_fail(session, name="rolled-back")
        session.add(_ConnTestWidget(name="next-row"))
    assert await _widget_names() == {"batch-survives", "next-row"}


@transaction(isolate=True)
async def _add_widget_then_fail_isolated(session: AsyncSession, *, name: str) -> None:
    await _add_widget_then_fail(session, name=name)


@pytest.mark.asyncio
async def test_isolate_true_takes_the_savepoint_on_the_callees_behalf(engine_and_session: None) -> None:
    async with transaction() as session:
        session.add(_ConnTestWidget(name="outer-survives"))
        with pytest.raises(ValueError, match="callee failed"):
            await _add_widget_then_fail_isolated(session, name="rolled-back")
    assert await _widget_names() == {"outer-survives"}


@pytest.mark.asyncio
async def test_the_session_is_bound_by_name_not_by_scanning_for_one(engine_and_session: None) -> None:

    @transaction
    async def not_session_first(name: str, session: AsyncSession | None = None) -> str:
        session.add(_ConnTestWidget(name=name))
        return type(name).__name__

    assert await not_session_first("late-param") == "str"
    assert await _widget_names() == {"late-param"}

    @transaction
    async def takes_a_session_as_data(session: AsyncSession, *, audited: AsyncSession, name: str) -> None:
        session.add(_ConnTestWidget(name=name))

    async with session() as other:
        await takes_a_session_as_data(audited=other, name="data-session")
    assert await _widget_names() == {"late-param", "data-session"}


def test_a_function_with_no_session_parameter_is_rejected_at_import() -> None:
    with pytest.raises(TypeError, match="has no 'session' parameter"):

        @transaction
        async def no_session(name: str) -> None: ...

    with pytest.raises(TypeError, match="positional-only"):

        @transaction
        async def positional_only(session: AsyncSession, /) -> None: ...


@pytest.mark.asyncio
async def test_a_positional_call_that_omits_the_session_is_refused(engine_and_session: None) -> None:
    with pytest.raises(TypeError, match="got str for its 'session' parameter"):
        await _add_widget("owned")


@pytest.mark.asyncio
async def test_transactional_detects_the_session_on_an_instance_method(engine_and_session: None) -> None:

    class Service:
        @transaction
        async def add_widget(self, session: AsyncSession, name: str) -> None:
            session.add(_ConnTestWidget(name=name))

    async with transaction() as session:
        await Service().add_widget(session, "method")
        await Service().add_widget(session=session, name="method-kw")
    assert await _widget_names() == {"method", "method-kw"}


@pytest.mark.asyncio
async def test_schema_translate_map(postgres_url_str: str, fresh_schema: str) -> None:
    target = fresh_schema + "_map"
    engine = create_async_engine(
        postgres_url_str,
        execution_options={
            "schema_translate_map": {
                None: target,
                "forktex_grid": target,
            }
        },
    )
    async with engine.begin() as conn:
        await conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{target}"'))
        await conn.run_sync(BaseDBModel.metadata.create_all)

    maker = sessions_for(engine)
    async with maker() as session:
        session.add(_ConnTestWidget(name="gamma"))
        await session.commit()

    async with engine.connect() as conn:
        rows = (
            await conn.execute(sa.text(f"SELECT name FROM \"{target}\".conn_test_widget WHERE name = 'gamma'"))
        ).fetchall()
    assert len(rows) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_dependency_works_in_fastapi(postgres_url_str: str, fresh_schema: str) -> None:
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    await init_engine(postgres_url_str)
    try:
        app = FastAPI()

        @app.get("/probe")
        async def _probe(session: AsyncSession = Depends(transaction.dependency)) -> dict[str, object]:
            value = (await session.execute(sa.text("SELECT 42"))).scalar_one()
            return {"is_session": isinstance(session, AsyncSession), "value": value}

        body = TestClient(app).get("/probe").json()
        assert body["is_session"] is True
        assert body["value"] == 42
    finally:
        await close_engine()


def test_database_construction_is_lazy() -> None:
    from forktex.database import Database

    db = Database(
        "postgresql+asyncpg://nobody:nothing@nonexistent.invalid:1/none",
        schema_translate_map={"forktex_flow": "somewhere"},
    )
    assert db.schema_translate_map == {"forktex_flow": "somewhere"}
    assert db.engine is not None


def test_independent_handles_own_independent_pools() -> None:
    from forktex.database import Database

    a = Database("postgresql+asyncpg://x:y@h/d")
    b = Database("postgresql+asyncpg://x:y@h/d")
    assert a.engine is not b.engine
    assert a.sessionmaker is not b.sessionmaker


@pytest.mark.asyncio
async def test_a_handles_transaction_commits_and_rolls_back(postgres_url_str: str) -> None:
    from forktex.database import Database

    db = Database(postgres_url_str)
    try:
        async with db.session() as session:
            assert (await session.execute(sa.text("SELECT 1"))).scalar_one() == 1

        with pytest.raises(ValueError):
            async with db.session() as session:
                await session.execute(sa.text("SELECT 1"))
                raise ValueError("boom")
        assert db.engine.pool.checkedout() == 0
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_a_caught_constraint_violation_needs_a_savepoint(engine_and_session: None) -> None:
    from forktex.database.crud import create
    from forktex.error import AlreadyExistsError

    async with transaction() as opened:
        await create(opened, _ConnTestUnique, slug="taken")

    with pytest.raises(PendingRollbackError):
        async with transaction() as opened:
            with pytest.raises(AlreadyExistsError):
                await create(opened, _ConnTestUnique, slug="taken")
            await create(opened, _ConnTestUnique, slug="next")

    async with transaction() as opened:
        with pytest.raises(AlreadyExistsError):
            async with savepoint(opened):
                await create(opened, _ConnTestUnique, slug="taken")
        await create(opened, _ConnTestUnique, slug="next")

    async with session() as plain:
        slugs = set((await plain.execute(sa.select(_ConnTestUnique.slug))).scalars())
    assert slugs == {"taken", "next"}


@pytest.mark.asyncio
async def test_the_session_parameter_may_be_named_something_else(engine_and_session: None) -> None:
    @transaction(param="db")
    async def add_under_another_name(db: AsyncSession, *, name: str) -> None:
        db.add(_ConnTestWidget(name=name))

    await add_under_another_name(name="renamed")
    assert await _widget_names() == {"renamed"}

    async with transaction() as session:
        await add_under_another_name(db=session, name="joined")
        assert await _widget_names() == {"renamed"}
    assert await _widget_names() == {"renamed", "joined"}


def test_a_renamed_session_parameter_must_still_exist() -> None:
    with pytest.raises(TypeError, match="has no 'db' parameter"):

        @transaction(param="db")
        async def no_such_parameter(session: AsyncSession) -> None: ...


@pytest.mark.asyncio
async def test_an_owned_handle_hands_out_both_kinds_of_session(postgres_url_str: str) -> None:
    db = Database(postgres_url_str)
    try:
        async with db.transaction() as owned:
            with pytest.raises(TransactionBoundaryError):
                await owned.commit()
        async with db.session() as unmanaged:
            await unmanaged.commit()
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_init_engine_hands_back_nothing_and_session_is_the_commit_capable_one(
    postgres_url_str: str, fresh_schema: str
) -> None:
    assert await init_engine(postgres_url_str, schema_translate_map={None: fresh_schema}) is None
    async with get_engine().begin() as conn:
        await conn.run_sync(BaseDBModel.metadata.create_all)
    async with session() as raw:
        raw.add(_ConnTestWidget(name="raw-factory"))
        await raw.commit()
    assert await _widget_names() == {"raw-factory"}
    await close_engine()


@pytest.mark.asyncio
async def test_a_handles_sessionmaker_hands_out_a_session_that_commits(postgres_url_str: str) -> None:
    db = Database(postgres_url_str)
    try:
        async with db.sessionmaker() as raw:
            await raw.execute(sa.text("SELECT 1"))
            await raw.commit()
            await raw.rollback()
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_a_session_left_with_uncommitted_writes_refuses_to_close_quietly(
    engine_and_session: None,
) -> None:
    with pytest.raises(TransactionBoundaryError, match="uncommitted writes"):
        async with session() as plain:
            plain.add(_ConnTestWidget(name="forgotten"))

    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_a_flushed_but_uncommitted_session_is_refused_too(engine_and_session: None) -> None:
    with pytest.raises(TransactionBoundaryError, match="uncommitted writes"):
        async with session() as plain:
            plain.add(_ConnTestWidget(name="flushed"))
            await plain.flush()

    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_core_dml_through_a_session_counts_as_a_write(engine_and_session: None) -> None:
    with pytest.raises(TransactionBoundaryError, match="uncommitted writes"):
        async with session() as plain:
            await plain.execute(sa.insert(_ConnTestWidget).values(name="core"))

    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_a_read_only_session_closes_without_complaint(engine_and_session: None) -> None:
    async with session() as plain:
        assert (await plain.execute(sa.select(_ConnTestWidget.name))).scalars().all() == []


@pytest.mark.asyncio
async def test_a_rolled_back_session_closes_without_complaint(engine_and_session: None) -> None:
    async with session() as plain:
        plain.add(_ConnTestWidget(name="abandoned"))
        await plain.rollback()

    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_writes_after_a_commit_are_refused_like_any_other(engine_and_session: None) -> None:
    with pytest.raises(TransactionBoundaryError, match="uncommitted writes"):
        async with session() as plain:
            plain.add(_ConnTestWidget(name="kept"))
            await plain.commit()
            plain.add(_ConnTestWidget(name="trailing"))

    assert await _widget_names() == {"kept"}


@pytest.mark.asyncio
async def test_raw_sql_writes_are_opaque_and_go_untracked(engine_and_session: None, fresh_schema: str) -> None:
    async with session() as plain:
        await plain.execute(sa.text(f"INSERT INTO {fresh_schema}.conn_test_widget (name) VALUES ('opaque')"))

    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_the_block_that_raised_first_is_not_masked_by_the_boundary_check(
    engine_and_session: None,
) -> None:
    with pytest.raises(ValueError, match="caller failed"):
        async with session() as plain:
            plain.add(_ConnTestWidget(name="lost"))
            raise ValueError("caller failed")

    assert await _widget_names() == set()


@pytest.mark.asyncio
async def test_isolate_is_a_decorator_only_form(engine_and_session: None) -> None:
    with pytest.raises(TransactionBoundaryError, match="decorator-only"):
        async with transaction(isolate=True):
            pass


@pytest.mark.asyncio
async def test_a_test_suite_can_override_the_dependency(postgres_url_str: str) -> None:
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    await init_engine(postgres_url_str)
    try:
        app = FastAPI()

        @app.get("/probe")
        async def _probe(session: AsyncSession = Depends(transaction.dependency)) -> dict[str, object]:
            return {"overridden": getattr(session, "overridden", False)}

        assert transaction.dependency is not transaction.dependency

        async def _fixture_session() -> AsyncIterator[object]:
            opened = require_default().sessionmaker()
            opened.overridden = True
            yield opened
            await opened.close()

        app.dependency_overrides[transaction.dependency] = _fixture_session
        assert TestClient(app).get("/probe").json() == {"overridden": True}
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_re_initialising_disposes_the_pool_it_replaces(postgres_url_str: str) -> None:
    await init_engine(postgres_url_str)
    try:
        replaced = require_default()
        pool = replaced.engine.pool
        async with session():
            pass

        await init_engine(postgres_url_str)

        assert require_default() is not replaced
        assert replaced.engine.pool is not pool
    finally:
        await close_engine()
