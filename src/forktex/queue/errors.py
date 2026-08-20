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


"""Queue module errors."""

from __future__ import annotations

from forktex.error import AppError, AppErrorCode


class QueueError(AppError, RuntimeError):
    """Raised on queue configuration or connection errors.

    Inherits from **both** bases deliberately. ``AppError`` gives it a
    ``code``/``details`` and makes it renderable by any transport that
    already handles ``AppError`` (e.g. an HTTP envelope middleware)
    instead of surfacing as a masked 500. ``RuntimeError`` is
    retained so pre-existing ``except RuntimeError`` call sites keep
    working unchanged — both derive from ``Exception``, so the MRO is
    consistent and neither guarantee is lost.
    """

    code = AppErrorCode.INTERNAL


__all__ = ["QueueError"]
