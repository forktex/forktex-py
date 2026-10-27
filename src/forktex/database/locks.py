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

import zlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import sqlalchemy as sa

from forktex.log import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

logger = get_logger(__name__)

_UNSIGNED_64_WRAP = 1 << 64


def advisory_key(*parts: object) -> int:
    if not parts:
        raise ValueError("advisory_key requires at least one part")
    return zlib.crc32("\x00".join(str(p) for p in parts).encode())


def key_from_uuid(value: object) -> int:
    as_int = getattr(value, "int", None)
    if as_int is None:
        raise TypeError(f"expected a UUID, got {type(value).__name__}")
    return _as_signed_bigint((as_int & 0xFFFFFFFFFFFFFFFF) ^ (as_int >> 64))


def _as_signed_bigint(unsigned: int) -> int:
    return unsigned - _UNSIGNED_64_WRAP if unsigned >= 1 << 63 else unsigned


async def xact_lock(session: AsyncSession, key: int) -> None:
    await session.execute(sa.select(sa.func.pg_advisory_xact_lock(key)))


@asynccontextmanager
async def advisory_lock(engine: AsyncEngine, key: int) -> AsyncGenerator[AsyncConnection]:
    async with engine.connect() as conn:
        await conn.execute(sa.select(sa.func.pg_advisory_lock(key)))
        await conn.commit()
        try:
            yield conn
        finally:
            await _release(conn, key)


@asynccontextmanager
async def try_advisory_lock(engine: AsyncEngine, key: int) -> AsyncGenerator[bool]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.select(sa.func.pg_try_advisory_lock(key)))
        acquired: bool = result.scalar_one()
        await conn.commit()
        try:
            yield acquired
        finally:
            if acquired:
                await _release(conn, key)


async def _release(conn: AsyncConnection, key: int) -> None:
    try:
        await _discard_pending_work_and_unlock(conn, key)
    except Exception:
        logger.warning("pg_advisory_unlock failed; closing the connection so Postgres releases the lock", exc_info=True)
        await conn.invalidate()


async def _discard_pending_work_and_unlock(conn: AsyncConnection, key: int) -> None:
    await conn.rollback()
    await conn.execute(sa.select(sa.func.pg_advisory_unlock(key)))
    await conn.commit()


__all__ = [
    "advisory_key",
    "advisory_lock",
    "key_from_uuid",
    "try_advisory_lock",
    "xact_lock",
]
