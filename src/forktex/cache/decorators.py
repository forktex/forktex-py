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

"""Cache decorator for async functions."""

import functools
import hashlib
from collections.abc import Callable

from pydantic import BaseModel

from forktex.cache.ops import fetch_or_set, fetch_swr


def _default_key(func: Callable, args: tuple, kwargs: dict) -> str:
    """A cache key derived from the qualified function name and its arguments.

    ``kwargs`` are sorted, because a dict's repr preserves insertion order and
    ``f(a=1, b=2)`` / ``f(b=2, a=1)`` are the same call — hashing them apart is a
    permanent miss that looks like a cache which simply never helps.

    The argument text is still ``repr``, so the key is only as stable as the
    arguments' reprs. A value whose type falls back to ``object.__repr__``
    embeds its ``id()``: the entry is never re-hit, and two objects that happen
    to share a repr collide. Pass ``key_builder`` for arguments that are not
    reliably representable — identity is not a cache key.
    """
    rendered_kwargs = ", ".join(f"{k}={kwargs[k]!r}" for k in sorted(kwargs))
    raw = f"{func.__module__}.{func.__qualname__}:{args!r}:{{{rendered_kwargs}}}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cached(
    *,
    ttl: int = 60,
    stale_ttl: int | None = None,
    key_builder: Callable | None = None,
    response_model: type[BaseModel] | None = None,
) -> Callable:
    """Decorator to cache async function results in Redis.

    Args:
        ttl: Cache TTL in seconds (or refresh threshold for SWR).
        stale_ttl: If set, uses stale-while-revalidate strategy.
        key_builder: Custom function to build cache key from args.
        response_model: Pydantic model for deserialization.

    Usage::

        @cached(ttl=300, response_model=UserProfile)
        async def get_profile(user_id: str) -> UserProfile:
            ...

        @cached(ttl=60, stale_ttl=300)
        async def get_feed(org_id: str) -> dict:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: object, **kwargs: object) -> object:
            key = key_builder(*args, **kwargs) if key_builder else _default_key(fn, args, kwargs)
            if stale_ttl is not None:
                return await fetch_swr(key, ttl, stale_ttl, fn, args, kwargs, response_model)
            return await fetch_or_set(key, ttl, fn, args, kwargs, response_model)

        return wrapper

    return decorator


__all__ = ["cached"]
