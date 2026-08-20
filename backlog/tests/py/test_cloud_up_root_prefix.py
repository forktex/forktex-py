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

"""Guard the build-context `root_prefix` derivation in `forktex cloud up`.

`_run_local` derives the SDK's `root_prefix` as the relative hop from the
generated compose file's directory up to the project root
(`os.path.relpath(project_root, compose_target.parent)`) instead of assuming a
fixed depth. The original `network/network` bug came from that hop being
hard-coded and silently drifting when the compose moved into `.forktex/cache/`.
This pins the invariant: for the standard layout the derived prefix is `../..`,
and it always points back at the project root.
"""

import os
from pathlib import Path

from forktex.substrate.paths import compose_path


def _derived_root_prefix(project_root: Path) -> str:
    compose_target = compose_path(project_root, "local")
    return os.path.relpath(project_root, compose_target.parent)


def test_derived_prefix_is_two_levels_for_cache_layout(tmp_path):
    # .forktex/cache/ is two directories below the project root.
    assert _derived_root_prefix(tmp_path) == os.path.join("..", "..")


def test_derived_prefix_round_trips_to_project_root(tmp_path):
    compose_dir = compose_path(tmp_path, "local").parent
    prefix = _derived_root_prefix(tmp_path)
    assert (compose_dir / prefix).resolve() == tmp_path.resolve()
