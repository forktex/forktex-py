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

"""SDK exception → ``click.ClickException`` translation.

Cloud subcommands talk to ``forktex_cloud.client.ForktexCloudClient``,
which raises ``CloudAPIError`` for non-2xx responses and any
``httpx.HTTPError`` subclass for network failures. Without this
module those bubble out as raw tracebacks. The decorator below wraps
each Click command so the user sees a single-line, exit-code-1
``ClickException`` instead.

Usage::

    from forktex.agent.cloud.errors import translate_cloud_errors

    @cloud.command("down")
    @translate_cloud_errors
    async def down_cmd(...):
        ...

The decorator is async-friendly (it inspects the wrapped callable
and produces a coroutine wrapper when needed) so it composes with
asyncclick. Already-translated ``ClickException``s pass through
unchanged.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, TypeVar

import asyncclick as click
import httpx
from forktex_cloud.client import CloudAPIError


F = TypeVar("F", bound=Callable[..., Any])


__all__ = ["translate_cloud_errors"]


def _format_api_error(exc: CloudAPIError) -> str:
    code = getattr(exc, "status_code", "?")
    detail = getattr(exc, "detail", str(exc))
    if code == 401:
        return (
            f"Cloud API rejected the request (401 unauthorised): {detail}\n"
            "Run `forktex cloud connect` to refresh your credentials."
        )
    if code == 403:
        return f"Cloud API forbidden (403): {detail}"
    if code == 404:
        return f"Cloud API not found (404): {detail}"
    if code in (500, 502, 503, 504):
        return (
            f"Cloud controller unhealthy (HTTP {code}): {detail}\n"
            "Try again in a moment, or check `forktex cloud status`."
        )
    return f"Cloud API error (HTTP {code}): {detail}"


def _format_network_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.ConnectError):
        return (
            f"Cannot reach the Cloud controller: {exc}\n"
            "Verify your `controller` setting "
            "(`forktex cloud status`) and that you're online."
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"Cloud controller timed out: {exc}"
    return f"Cloud controller request failed: {exc}"


def translate_cloud_errors(func: F) -> F:
    """Catch ``CloudAPIError`` and ``httpx.HTTPError`` from *func* and
    re-raise as ``click.ClickException`` with a user-friendly message.

    Pass-through for ``ClickException`` (already translated upstream)
    and for any other exception (real bugs should surface, not be
    swallowed). Works on sync and async callables.
    """

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except click.ClickException:
                raise
            except CloudAPIError as exc:
                raise click.ClickException(_format_api_error(exc)) from exc
            except httpx.HTTPError as exc:
                raise click.ClickException(_format_network_error(exc)) from exc

        return _async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except click.ClickException:
            raise
        except CloudAPIError as exc:
            raise click.ClickException(_format_api_error(exc)) from exc
        except httpx.HTTPError as exc:
            raise click.ClickException(_format_network_error(exc)) from exc

    return _sync_wrapper  # type: ignore[return-value]
