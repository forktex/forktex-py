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


"""Database module errors.

``ConflictError`` — raised by the CRUD layer on a uniqueness violation — is not
redefined here: it belongs to the shared vocabulary in ``forktex.error`` and is
re-exported by ``forktex.database`` so one handler catches both import paths.
"""

from __future__ import annotations

from forktex.error import AppError, AppErrorCode


class DatabaseNotInitializedError(AppError, RuntimeError):
    """A session was requested before :func:`init_engine` configured a default.

    Inherits both bases deliberately, the same way ``queue.QueueError`` does:
    ``AppError`` gives it a ``code`` and makes it renderable by any transport
    that already handles ``AppError``, while ``RuntimeError`` keeps
    pre-existing ``except RuntimeError`` call sites working. ``INTERNAL``
    because a missing ``init_engine()`` is a wiring mistake, not something the
    caller of an endpoint can fix or retry.
    """

    code = AppErrorCode.INTERNAL


__all__ = ["DatabaseNotInitializedError"]
