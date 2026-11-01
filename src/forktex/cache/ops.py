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

from collections.abc import Callable

from pydantic import BaseModel

from forktex.cache.cache import LOCK_TTL
from forktex.cache.connection import default


async def get(key: str) -> str | None:
    cache = default()
    return None if cache is None else await cache.get(key)


async def set(key: str, value: str, ex: int) -> None:
    cache = default()
    if cache is not None:
        await cache.set(key, value, ex=ex)


async def delete(key: str) -> None:
    cache = default()
    if cache is not None:
        await cache.delete(key)


async def invalidate_key(key: str) -> None:
    await delete(key)


async def invalidate_prefix(prefix: str) -> int:
    cache = default()
    return 0 if cache is None else await cache.invalidate_prefix(prefix)


async def fetch_or_set(
    key: str,
    ttl: int,
    fn: Callable,
    args: tuple,
    kwargs: dict,
    response_model: type[BaseModel] | None,
) -> object:
    cache = default()
    if cache is None:
        return await fn(*args, **kwargs)
    return await cache.fetch_or_set(key, ttl, fn, args, kwargs, response_model)


async def fetch_swr(
    key: str,
    ttl: int,
    stale_ttl: int,
    fn: Callable,
    args: tuple,
    kwargs: dict,
    response_model: type[BaseModel] | None,
) -> object:
    cache = default()
    if cache is None:
        return await fn(*args, **kwargs)
    return await cache.fetch_swr(key, ttl, stale_ttl, fn, args, kwargs, response_model)


async def shutdown_background_tasks() -> None:
    cache = default()
    if cache is not None:
        await cache.shutdown_background_tasks()


__all__ = [
    "LOCK_TTL",
    "delete",
    "fetch_or_set",
    "fetch_swr",
    "get",
    "invalidate_key",
    "invalidate_prefix",
    "set",
    "shutdown_background_tasks",
]
