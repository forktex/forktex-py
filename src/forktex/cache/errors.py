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


"""Cache module errors.

``AppError`` subclasses, so a consumer's single ``except AppError`` boundary
renders them like every other forktex error instead of letting a bare
``RuntimeError`` escape as a masked 500 — see ``forktex.error``.

Both also inherit ``RuntimeError``, the same way
``database.DatabaseNotInitializedError`` and ``queue.QueueError`` do: this
module used to raise a plain ``RuntimeError``, and ``cache.ops._safe_client``
catches that to degrade to a cache miss. Keeping the base means every existing
``except RuntimeError`` call site — inside this library and out — still works.
"""

from __future__ import annotations

from forktex.error import AppError, AppErrorCode


class CacheError(AppError, RuntimeError):
    """Base class for cache module errors."""

    code = AppErrorCode.INTERNAL


class CacheNotInitializedError(CacheError):
    """Raised when the client is requested before :func:`init` configured one.

    ``INTERNAL`` because a missing ``init()`` is a wiring mistake in the host
    process, not something the caller of an endpoint can fix or retry.
    """


class CacheInitializationError(CacheError):
    """Raised when :func:`init` cannot reach Redis.

    The client is left unset, so :func:`available` keeps reporting ``False``
    rather than handing out a connection that never worked.
    """

    code = AppErrorCode.UNAVAILABLE


__all__ = ["CacheError", "CacheInitializationError", "CacheNotInitializedError"]
