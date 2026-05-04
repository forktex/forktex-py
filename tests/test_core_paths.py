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

from forktex.core.paths import (
    FORKTEX_MANIFEST,
    find_project_root,
    get_manifest_path,
    has_manifest,
    require_project_root,
)


def test_require_project_root_from_test_file():
    root = require_project_root(__file__)
    assert root.name == "forktex-py"
    assert (root / FORKTEX_MANIFEST).is_file()


def test_find_project_root_from_nested_path():
    root = require_project_root(__file__)
    nested = root / "src" / "forktex" / "fsd" / "models.py"
    root = find_project_root(nested)
    assert root is not None
    assert root.name == "forktex-py"


def test_manifest_helpers_use_canonical_name():
    root = require_project_root(__file__)
    assert get_manifest_path(root) == root / FORKTEX_MANIFEST
    assert has_manifest(root)
