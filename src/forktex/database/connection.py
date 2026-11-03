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
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from types import TracebackType
from typing import overload

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import ORMExecuteState, Session

from forktex.database.errors import (
    DatabaseNotInitializedError,
    DatabaseUnreachableError,
    TransactionBoundaryError,
)
from forktex.database.integrity import integrity_boundary
from forktex.log import get_logger

logger = get_logger(__name__)

_BOUNDARY_REFUSED = (
    "{call}() is not available here: this session's transaction belongs to the "
    "transaction() block that opened it. Raise to abort the whole unit of work, wrap the "
    "part that may fail in savepoint(session), or open session() to own the boundary yourself."
)

_UNCOMMITTED_WRITES = (
    "session() block ended with uncommitted writes, which have been discarded. A session() "
    "hands you the boundary: commit before leaving the block, or use transaction(), which "
    "commits for you."
)

_ISOLATE_WITHOUT_OUTER = (
    "transaction(isolate=True) is a decorator-only form: it opens a savepoint inside the "
    "caller's session, and an `async with` block has no caller's session to nest in."
)


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
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(bind=engine, expire_on_commit=False)
        self._managed: async_sessionmaker[_ManagedSession] = async_sessionmaker(
            bind=engine, expire_on_commit=False, class_=_ManagedSession
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    def transaction(self) -> AbstractAsyncContextManager[AsyncSession]:
        return _managed_session(self._managed)

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return _unmanaged_session(self._sessionmaker)

    async def verify(self) -> None:
        try:
            async with self._engine.connect() as conn:
                await conn.execute(sa.select(sa.literal(1)))
        except Exception as exc:
            raise DatabaseUnreachableError("database is not reachable") from exc

    async def dispose(self) -> None:
        await self._engine.dispose()


async def init_engine(
    db_url: str,
    *,
    echo: bool = False,
    schema_translate_map: dict[str, str | None] | None = None,
    **engine_kwargs: object,
) -> None:
    global _default
    previous = _default
    _default = Database(db_url, echo=echo, schema_translate_map=schema_translate_map, **engine_kwargs)
    if previous is not None:
        await previous.dispose()
    logger.debug(
        "database engine initialised",
        extra={"schema_translate_map": schema_translate_map},
    )


async def verify() -> None:
    await require_default().verify()


async def close_engine() -> None:
    global _default
    if _default is not None:
        await _default.dispose()
        _default = None


def default() -> Database | None:
    return _default


def require_default() -> Database:
    if _default is None:
        raise DatabaseNotInitializedError("Engine/sessionmaker not initialized — call init_engine() first")
    return _default


def get_engine() -> AsyncEngine:
    return require_default().engine


def session() -> AbstractAsyncContextManager[AsyncSession]:
    return require_default().session()


@asynccontextmanager
async def savepoint(session: AsyncSession) -> AsyncGenerator[None]:
    async with session.begin_nested():
        yield


def _bind_session[R](fn: Callable[..., Awaitable[R]], *, isolate: bool, param: str) -> Callable[..., Awaitable[R]]:
    signature = inspect.signature(fn)
    target = signature.parameters.get(param)
    if target is None:
        raise TypeError(f"@transaction: {fn.__qualname__} has no {param!r} parameter to bind a session to")
    if target.kind is inspect.Parameter.POSITIONAL_ONLY:
        raise TypeError(
            f"@transaction: {fn.__qualname__}'s {param!r} parameter "
            f"is positional-only, so a session cannot be bound to it by name"
        )

    @functools.wraps(fn)
    async def wrapper(*args: object, **kwargs: object) -> R:
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
        async with _TransactionScope(isolate=False, param=param) as opened:
            if param in bound.arguments:
                bound.arguments[param] = opened
                return await fn(*bound.args, **bound.kwargs)
            return await fn(*args, **{**kwargs, param: opened})

    return wrapper


class _TransactionScope:
    _opened: AbstractAsyncContextManager[AsyncSession]

    def __init__(self, *, isolate: bool, param: str) -> None:
        self._isolate = isolate
        self._param = param

    async def __aenter__(self) -> AsyncSession:
        if self._isolate:
            raise TransactionBoundaryError(_ISOLATE_WITHOUT_OUTER)
        self._opened = require_default().transaction()
        return await self._opened.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        return await self._opened.__aexit__(exc_type, exc, tb)

    def __call__[R](self, fn: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        return _bind_session(fn, isolate=self._isolate, param=self._param)


class _Transaction:
    @overload
    def __call__[R](self, fn: Callable[..., Awaitable[R]], /) -> Callable[..., Awaitable[R]]: ...

    @overload
    def __call__(self, fn: None = None, /, *, isolate: bool = False, param: str = "session") -> _TransactionScope: ...

    def __call__(
        self,
        fn: Callable[..., Awaitable[object]] | None = None,
        /,
        *,
        isolate: bool = False,
        param: str = "session",
    ) -> Callable[..., Awaitable[object]] | _TransactionScope:
        scope = _TransactionScope(isolate=isolate, param=param)
        return scope(fn) if fn is not None else scope

    async def dependency(self) -> AsyncGenerator[AsyncSession]:
        async with require_default().transaction() as bound:
            yield bound


transaction = _Transaction()


class _ManagedSession(AsyncSession):
    async def commit(self) -> None:
        raise TransactionBoundaryError(_BOUNDARY_REFUSED.format(call="commit"))

    async def rollback(self) -> None:
        raise TransactionBoundaryError(_BOUNDARY_REFUSED.format(call="rollback"))

    def begin(self) -> AsyncSessionTransaction:
        raise TransactionBoundaryError(_BOUNDARY_REFUSED.format(call="begin"))


class _WriteWatch:
    def __init__(self, sync_session: Session) -> None:
        self._session = sync_session
        self._written = False
        event.listen(sync_session, "after_flush", self._wrote)
        event.listen(sync_session, "do_orm_execute", self._executed)
        event.listen(sync_session, "after_commit", self._settled)
        event.listen(sync_session, "after_soft_rollback", self._settled)

    def _wrote(self, _session: Session, _context: object) -> None:
        self._written = True

    def _executed(self, state: ORMExecuteState) -> None:
        if state.is_insert or state.is_update or state.is_delete:
            self._written = True

    def _settled(self, *_args: object) -> None:
        self._written = False

    def pending(self) -> bool:
        return self._written or bool(self._session.new or self._session.dirty or self._session.deleted)


@asynccontextmanager
async def _managed_session(
    sessionmaker: async_sessionmaker[_ManagedSession],
) -> AsyncGenerator[AsyncSession]:
    async with sessionmaker() as opened:
        try:
            yield opened
        except Exception:
            await AsyncSession.rollback(opened)
            raise
        async with integrity_boundary():
            await AsyncSession.commit(opened)


@asynccontextmanager
async def _unmanaged_session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession]:
    async with sessionmaker() as opened:
        watch = _WriteWatch(opened.sync_session)
        yield opened
        if watch.pending():
            raise TransactionBoundaryError(_UNCOMMITTED_WRITES)


_default: Database | None = None


__all__ = [
    "Database",
    "close_engine",
    "default",
    "get_engine",
    "init_engine",
    "require_default",
    "savepoint",
    "session",
    "transaction",
    "verify",
]
