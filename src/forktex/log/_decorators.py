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

import functools
import inspect
import logging
import time
from collections.abc import Callable
from typing import cast, overload

from forktex.log._context import async_trace_context, trace_context


@overload
def traced[**P, R](
    fn: Callable[P, R],
    *,
    name: str | None = None,
    level: int = logging.INFO,
) -> Callable[P, R]: ...


@overload
def traced[**P, R](
    fn: None = None,
    *,
    name: str | None = None,
    level: int = logging.INFO,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def traced[**P, R](
    fn: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    level: int = logging.INFO,
) -> Callable[..., object]:

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        label = name or func.__qualname__
        log = logging.getLogger(func.__module__)

        if inspect.isasyncgenfunction(func) or inspect.isgeneratorfunction(func):
            raise TypeError(
                f"@traced cannot wrap the generator {func.__qualname__}: the scope would close "
                f"at the first yield, timing construction instead of iteration"
            )

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                async with async_trace_context():
                    log.log(level, "%s started", label)
                    start = time.monotonic()
                    try:
                        result = await func(*args, **kwargs)
                    except Exception:
                        log.exception("%s failed", label)
                        raise
                    duration_ms = round((time.monotonic() - start) * 1000, 2)
                    log.log(level, "%s finished", label, extra={"duration_ms": duration_ms})
                    return result

            return cast(Callable[P, R], async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with trace_context():
                log.log(level, "%s started", label)
                start = time.monotonic()
                try:
                    result = func(*args, **kwargs)
                except Exception:
                    log.exception("%s failed", label)
                    raise
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                log.log(level, "%s finished", label, extra={"duration_ms": duration_ms})
                return cast(R, result)

        return sync_wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


__all__ = ["traced"]
