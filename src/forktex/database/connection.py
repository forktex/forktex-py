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


import functools
import inspect
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
    create_async_engine,
)

from forktex.database.errors import DatabaseNotInitializedError, TransactionBoundaryError
from forktex.log import get_logger

logger = get_logger(__name__)

_BOUNDARY_REFUSED = (
    "{call}() is not available here: this session's transaction belongs to the "
    "{owner} that opened it. Raise to abort the whole unit of work, wrap the part "
    "that may fail in savepoint(session), or open unmanaged_session() to own the "
    "boundary yourself."
)


class ManagedSession(AsyncSession):
    _boundary_owner: str | None = None

    async def commit(self) -> None:
        self._refuse_if_borrowed("commit")
        await super().commit()

    async def rollback(self) -> None:
        self._refuse_if_borrowed("rollback")
        await super().rollback()

    def begin(self) -> AsyncSessionTransaction:
        self._refuse_if_borrowed("begin")
        return super().begin()

    def _refuse_if_borrowed(self, call: str) -> None:
        if self._boundary_owner is not None:
            raise TransactionBoundaryError(_BOUNDARY_REFUSED.format(call=call, owner=self._boundary_owner))


class Database:
    def __init__(
        self,
        url: str,
        *,
        echo: bool = False,
        schema_translate_map: dict[str, str | None] | None = None,
        **engine_kwargs: object,
    ) -> None:
        self.url = url
        self.schema_translate_map = schema_translate_map
        engine = create_async_engine(url, echo=echo, **engine_kwargs)
        if schema_translate_map:
            engine = engine.execution_options(schema_translate_map=schema_translate_map)
        self._engine: AsyncEngine = engine
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=engine, expire_on_commit=False, class_=ManagedSession
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return _owned_session(self._sessionmaker, owner="get_session()")

    def unmanaged_session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return _unmanaged_session(self._sessionmaker)

    async def session_scope(self) -> AsyncGenerator[AsyncSession]:
        async with self.session() as session:
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()


@asynccontextmanager
async def _owned_session(sessionmaker: async_sessionmaker[AsyncSession], *, owner: str) -> AsyncGenerator[AsyncSession]:
    async with sessionmaker() as session:
        borrowed = isinstance(session, ManagedSession)
        if borrowed:
            session._boundary_owner = owner
        try:
            yield session
            if borrowed:
                session._boundary_owner = None
            await session.commit()
        except Exception:
            if borrowed:
                session._boundary_owner = None
            await session.rollback()
            raise


@asynccontextmanager
async def _unmanaged_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


@asynccontextmanager
async def savepoint(session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    async with session.begin_nested():
        yield session


_default: Database | None = None


def _require_default() -> Database:
    if _default is None:
        raise DatabaseNotInitializedError("Engine/sessionmaker not initialized — call init_engine() first")
    return _default


def init_engine(
    db_url: str,
    *,
    echo: bool = False,
    schema_translate_map: dict[str, str | None] | None = None,
    **engine_kwargs: object,
) -> async_sessionmaker:
    global _default
    if _default is not None:
        logger.warning(
            "init_engine() replacing an existing default engine without disposing it; "
            "call close_engine() first to release the old pool"
        )
    _default = Database(db_url, echo=echo, schema_translate_map=schema_translate_map, **engine_kwargs)
    logger.debug(
        "database engine initialised",
        extra={"schema_translate_map": schema_translate_map},
    )
    return _default.sessionmaker


async def close_engine() -> None:
    global _default
    if _default is not None:
        await _default.dispose()
        _default = None


def get_session() -> AbstractAsyncContextManager[AsyncSession]:
    return _require_default().session()


def unmanaged_session() -> AbstractAsyncContextManager[AsyncSession]:
    return _require_default().unmanaged_session()


async def session_scope() -> AsyncGenerator[AsyncSession]:
    async with get_session() as session:
        yield session


def __getattr__(name: str) -> object:
    if name == "engine":
        return None if _default is None else _default.engine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def with_transactional_session(
    func: Callable | None = None,
    /,
    *,
    isolate: bool = False,
    param: str = "session",
) -> Callable:

    def decorate(fn: Callable) -> Callable:
        signature = inspect.signature(fn)
        target = signature.parameters.get(param)
        if target is None:
            raise TypeError(
                f"@with_transactional_session: {fn.__qualname__} has no {param!r} parameter to bind a session to"
            )
        if target.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise TypeError(
                f"@with_transactional_session: {fn.__qualname__}'s {param!r} parameter "
                f"is positional-only, so a session cannot be bound to it by name"
            )

        @functools.wraps(fn)
        async def wrapper(*args: object, **kwargs: object) -> object:
            bound = signature.bind_partial(*args, **kwargs)
            provided = bound.arguments.get(param)
            if provided is not None and not isinstance(provided, AsyncSession):
                raise TypeError(
                    f"{fn.__qualname__}() got {type(provided).__name__} for its {param!r} "
                    f"parameter. Pass the other arguments by keyword: the session is not "
                    f"shuffled out of the way for a positional call."
                )
            if provided is not None:
                if isolate:
                    async with savepoint(provided):
                        return await fn(*args, **kwargs)
                return await fn(*args, **kwargs)
            async with get_session() as session:
                if param in bound.arguments:
                    bound.arguments[param] = session
                    return await fn(*bound.args, **bound.kwargs)
                return await fn(*args, **{**kwargs, param: session})

        return wrapper

    return decorate(func) if func is not None else decorate
