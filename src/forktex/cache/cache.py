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

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

import redis.asyncio as redis
from pydantic import BaseModel

from forktex.cache.errors import CacheUnreachableError
from forktex.cache.serialization import deserialize, serialize
from forktex.log import get_logger

logger = get_logger(__name__)

LOCK_TTL = 10


class Cache:
    def __init__(self, url: str, **client_kwargs: object) -> None:
        self.url = url
        self._client: redis.Redis = redis.from_url(url, encoding="utf-8", decode_responses=True, **client_kwargs)
        self._background_tasks: set[asyncio.Task[Any]] = set()

    @property
    def client(self) -> redis.Redis:
        return self._client

    async def verify(self) -> None:
        try:
            await self._client.ping()
        except Exception as exc:
            raise CacheUnreachableError(f"cache is not reachable ({_masked(self.url)})") from exc

    async def close(self) -> None:
        logger.info("Closing cache connection")
        try:
            await self._client.aclose()
            logger.info("Cache closed successfully")
        except Exception as e:
            logger.exception("Error closing cache: %s", e)

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except Exception:
            logger.exception("Cache GET failed")
            return None

    async def set(self, key: str, value: str, ex: int) -> None:
        if ex <= 0:
            return
        try:
            await self._client.set(key, value, ex=ex)
        except Exception:
            logger.exception("Cache SET failed")

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception:
            logger.exception("Cache DELETE failed")

    async def invalidate_key(self, key: str) -> None:
        await self.delete(key)

    async def invalidate_prefix(self, prefix: str) -> int:
        patterns = ["*"] if not prefix else [prefix, f"{prefix}:*"]
        try:
            keys: set[str] = set()
            for pattern in patterns:
                async for k in self._client.scan_iter(pattern):
                    keys.add(k)
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception:
            logger.exception("Cache invalidate_prefix failed")
            return 0

    async def fetch_or_set(
        self,
        key: str,
        ttl: int,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        response_model: type[BaseModel] | None,
    ) -> object:
        cached = await self.get(key)
        if cached:
            try:
                return deserialize(cached, response_model)
            except Exception:
                logger.warning("Cache decode failed, invalidating %s", key)
                await self.invalidate_key(key)

        result = await fn(*args, **kwargs)
        payload = serialize(result)
        await self.set(key, payload, ex=ttl)
        return deserialize(payload, response_model)

    async def fetch_swr(
        self,
        key: str,
        ttl: int,
        stale_ttl: int,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        response_model: type[BaseModel] | None,
    ) -> object:
        raw = await self.get(key)
        now = int(time.time())
        if raw:
            try:
                payload = json.loads(raw)
                age = now - payload["created_at"]
                value = deserialize(payload["value"], response_model)
            except Exception:
                logger.warning("SWR cache corrupted, invalidating %s", key)
                await self.invalidate_key(key)
            else:
                if age > ttl:
                    try:
                        await self._refresh_in_background(key, stale_ttl, fn, args, kwargs)
                    except Exception:
                        logger.warning("SWR background refresh could not start for %s", key, exc_info=True)
                return value

        result = await fn(*args, **kwargs)
        value = serialize(result)
        await self.set(key, json.dumps({"created_at": now, "value": value}), ex=stale_ttl)
        return deserialize(value, response_model)

    async def _refresh_in_background(self, key: str, stale_ttl: int, fn: Callable, args: tuple, kwargs: dict) -> None:
        lock_key = f"lock:{key}"
        acquired = await self._client.set(lock_key, "1", nx=True, ex=LOCK_TTL)
        if not acquired:
            return

        async def refresh() -> None:
            try:
                result = await fn(*args, **kwargs)
                payload = {"created_at": int(time.time()), "value": serialize(result)}
                await self.set(key, json.dumps(payload), ex=stale_ttl)
            except Exception:
                logger.exception("SWR refresh failed")
            finally:
                self._background_tasks.discard(asyncio.current_task())

        task = asyncio.create_task(refresh())
        self._background_tasks.add(task)

    async def shutdown_background_tasks(self) -> None:
        if self._background_tasks:
            logger.info("Waiting for %d SWR tasks to finish...", len(self._background_tasks))
            await asyncio.gather(*self._background_tasks, return_exceptions=True)


def _masked(url: str) -> str:
    return url.rsplit("@", 1)[-1] if "@" in url else url


__all__ = ["LOCK_TTL", "Cache"]
