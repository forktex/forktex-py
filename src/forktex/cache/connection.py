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

import redis.asyncio as redis

from forktex.cache.cache import Cache
from forktex.cache.errors import CacheNotInitializedError
from forktex.log import get_logger

logger = get_logger(__name__)

_default: Cache | None = None


def default() -> Cache | None:
    return _default


def require_default() -> Cache:
    if _default is None:
        logger.error("Cache client requested but not initialized")
        raise CacheNotInitializedError("Cache not initialized — call init() first")
    return _default


def available() -> bool:
    return _default is not None


def get_client() -> redis.Redis:
    return require_default().client


async def init(url: str) -> None:
    global _default
    previous = _default
    _default = Cache(url)
    if previous is not None:
        await previous.close()


async def verify() -> None:
    await require_default().verify()


async def close() -> None:
    global _default
    if _default is not None:
        await _default.close()
        _default = None


__all__ = ["available", "close", "default", "get_client", "init", "require_default"]
