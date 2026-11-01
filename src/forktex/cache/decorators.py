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
import hashlib
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar, cast

from pydantic import BaseModel

from forktex.cache.ops import fetch_or_set, fetch_swr

P = ParamSpec("P")
R = TypeVar("R")


def cached(
    *,
    ttl: int = 60,
    stale_ttl: int | None = None,
    key_builder: Callable[..., str] | None = None,
    response_model: type[BaseModel] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = key_builder(*args, **kwargs) if key_builder else _default_key(fn, args, kwargs)
            if stale_ttl is not None:
                return cast(R, await fetch_swr(key, ttl, stale_ttl, fn, args, kwargs, response_model))
            return cast(R, await fetch_or_set(key, ttl, fn, args, kwargs, response_model))

        return wrapper

    return decorator


def _default_key(func: Callable[..., object], args: tuple, kwargs: dict) -> str:
    rendered_kwargs = ", ".join(f"{k}={kwargs[k]!r}" for k in sorted(kwargs))
    raw = f"{func.__module__}.{func.__qualname__}:{args!r}:{{{rendered_kwargs}}}"
    return hashlib.sha256(raw.encode()).hexdigest()


__all__ = ["cached"]
