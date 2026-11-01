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
from typing import overload

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
    "transactional_session() block that opened it. Raise to abort the whole unit of "
    "work, wrap the part that may fail in savepoint(session), or open open_session() to "
    "own the boundary yourself."
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

    def transactional_session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return _transactional_session(self._managed)

    async def yield_transactional_session(self) -> AsyncGenerator[AsyncSession]:
        async with self.transactional_session() as bound:
            yield bound

    def open_session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return _open_session(self._sessionmaker)

    async def dispose(self) -> None:
        await self._engine.dispose()


def init_engine(
    db_url: str,
    *,
    echo: bool = False,
    schema_translate_map: dict[str, str | None] | None = None,
    **engine_kwargs: object,
) -> None:
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


def transactional_session() -> AbstractAsyncContextManager[AsyncSession]:
    return require_default().transactional_session()


async def yield_transactional_session() -> AsyncGenerator[AsyncSession]:
    async with transactional_session() as bound:
        yield bound


def open_session() -> AbstractAsyncContextManager[AsyncSession]:
    return require_default().open_session()


@asynccontextmanager
async def savepoint(session: AsyncSession) -> AsyncGenerator[None]:
    async with session.begin_nested():
        yield


@overload
def with_transactional_session[R](
    func: Callable[..., Awaitable[R]],
    /,
    *,
    isolate: bool = False,
    param: str = "session",
) -> Callable[..., Awaitable[R]]: ...


@overload
def with_transactional_session[R](
    func: None = None,
    /,
    *,
    isolate: bool = False,
    param: str = "session",
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]: ...


def with_transactional_session[R](
    func: Callable[..., Awaitable[R]] | None = None,
    /,
    *,
    isolate: bool = False,
    param: str = "session",
) -> Callable[..., object]:
    """The wrapper supplies `param` itself, so a caller omits it — which Python's
    type system cannot express. The return type is preserved; the parameters are not."""

    def decorate(fn: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
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
            async with transactional_session() as opened:
                if param in bound.arguments:
                    bound.arguments[param] = opened
                    return await fn(*bound.args, **bound.kwargs)
                return await fn(*args, **{**kwargs, param: opened})

        return wrapper

    return decorate(func) if func is not None else decorate


class _ManagedSession(AsyncSession):
    async def commit(self) -> None:
        raise TransactionBoundaryError(_BOUNDARY_REFUSED.format(call="commit"))

    async def rollback(self) -> None:
        raise TransactionBoundaryError(_BOUNDARY_REFUSED.format(call="rollback"))

    def begin(self) -> AsyncSessionTransaction:
        raise TransactionBoundaryError(_BOUNDARY_REFUSED.format(call="begin"))


@asynccontextmanager
async def _transactional_session(
    sessionmaker: async_sessionmaker[_ManagedSession],
) -> AsyncGenerator[AsyncSession]:
    async with sessionmaker() as opened:
        try:
            yield opened
        except Exception:
            await AsyncSession.rollback(opened)
            raise
        await AsyncSession.commit(opened)


@asynccontextmanager
async def _open_session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession]:
    async with sessionmaker() as opened:
        yield opened


_default: Database | None = None


__all__ = [
    "Database",
    "close_engine",
    "default",
    "get_engine",
    "init_engine",
    "open_session",
    "require_default",
    "savepoint",
    "transactional_session",
    "with_transactional_session",
    "yield_transactional_session",
]
