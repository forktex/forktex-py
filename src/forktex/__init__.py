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


import importlib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forktex import api, cache, database, error, iso, log, storage, types

try:
    __version__ = _pkg_version("forktex")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"


__all__ = [
    "__version__",
    "api",
    "cache",
    "database",
    "error",
    "iso",
    "log",
    "storage",
    "types",
]

_MODULES = frozenset(__all__) - {"__version__"}


def __getattr__(name: str) -> ModuleType:
    """Resolve `forktex.<module>` on first access.

    `import forktex` exposes all eight, but importing one must not drag in the
    others: `forktex.iso` is stdlib-only and `forktex.error` is pure Pydantic,
    while `api`, `cache`, `database` and `storage` pull FastAPI, redis,
    SQLAlchemy and botocore between them.
    """
    if name not in _MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{name}")
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted(__all__)
