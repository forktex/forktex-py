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

"""Guards for ``forktex.models`` lazy re-export surface.

The package exports its model classes lazily via ``__getattr__`` (keeps the
heavy submodules off the cold-import path) while declaring a *static* ``__all__``
+ ``TYPE_CHECKING`` imports so type-checkers can resolve every name. These tests
keep the static surface honest against the lazy ``_EXPORTS`` map.
"""

from __future__ import annotations

import importlib

import forktex.models as models


def test_all_matches_exports() -> None:
    """``__all__`` is the four base names plus every lazy export, in order."""
    base = ["ForkTexModel", "Identifiable", "Versioned", "Tagged"]
    assert models.__all__ == base + list(models._EXPORTS)


def test_every_lazy_export_resolves() -> None:
    """Each name in ``_EXPORTS`` is importable and lives in its declared module."""
    for name, module_path in models._EXPORTS.items():
        obj = getattr(models, name)
        assert obj is getattr(importlib.import_module(module_path), name)


def test_unknown_attribute_raises() -> None:
    import pytest

    with pytest.raises(AttributeError):
        _ = models.DoesNotExist  # type: ignore[attr-defined]
