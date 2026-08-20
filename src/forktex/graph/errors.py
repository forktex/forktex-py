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


"""Graph module errors.

Each keeps a builtin in its bases alongside the ``AppError`` type: these are
raised from id lookups and argument checks, so callers already catch
``KeyError``/``ValueError`` and must keep working.
"""

from __future__ import annotations

from forktex.error import AppErrorCode, BadRequestError, NotFoundError


class NodeNotFoundError(NotFoundError, KeyError):
    """An edge referenced a node id the graph does not contain.

    A ``NotFoundError`` so a graph miss carries the same contract as any other
    missing resource; ``KeyError`` stays in the bases because these are raised
    from id lookups and callers catch it as such.
    """

    code = AppErrorCode.NOT_FOUND


class InvalidDirectionError(BadRequestError, ValueError):
    """``neighbors(direction=…)`` was given something other than out/in/both.

    ``ValueError`` stays in the bases for the same reason as
    :class:`NodeNotFoundError`'s ``KeyError``: it is what callers already catch.
    """

    code = AppErrorCode.BAD_REQUEST


__all__ = ["InvalidDirectionError", "NodeNotFoundError"]
