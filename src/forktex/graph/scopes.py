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

"""Graph build scopes — project-local and host-OS."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forktex_cloud import paths as _cloud_paths


@dataclass(frozen=True)
class ProjectScope:
    """Build a graph rooted at one project (a directory with ``forktex.json``)."""

    root: Path

    @property
    def label(self) -> str:
        return "project"

    @property
    def forktex_dir(self) -> Path:
        return _cloud_paths.project_dir(self.root)


@dataclass(frozen=True)
class OSScope:
    """Build a graph rooted at the host-wide ``~/.forktex/`` directory."""

    @property
    def label(self) -> str:
        return "os"

    @property
    def forktex_dir(self) -> Path:
        return _cloud_paths.global_dir()

    @property
    def root(self) -> Path:
        return self.forktex_dir
