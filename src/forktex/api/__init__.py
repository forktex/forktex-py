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

"""The generic forktex tool API (the one HTTP + MCP surface).

Importing :func:`build_domains` is dependency-light (no FastAPI); building the
app via :func:`create_app` needs the ``[mcp]`` extra (FastAPI + fastapi_mcp).
"""

from typing import TYPE_CHECKING

from forktex.api.registry import build_domains

if TYPE_CHECKING:  # static visibility for `create_app` (runtime path is lazy below)
    from forktex.api.app import create_app

__all__ = ["build_domains", "create_app"]


def __getattr__(name: str):  # lazy — keep FastAPI out of the light import path
    if name == "create_app":
        from forktex.api.app import create_app

        return create_app
    raise AttributeError(name)
