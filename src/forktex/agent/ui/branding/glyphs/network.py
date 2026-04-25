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

"""Network — diagonals only, an X.

Faithful to ``cloud.forktex.com/assets/forktex-network-icon-*.svg``:
only the four diagonal arms (NE, SE, SW, NW) radiate from the centre;
the cardinals are absent. Diagonals span 4 rows × 8 cols so the corner
nodes land exactly at the bounding-box corners. 9-row × 17-column
canvas.
"""

GLYPH: list[str] = [
    "●               ●",
    "  ╲╲         ╱╱  ",
    "    ╲╲     ╱╱    ",
    "      ╲╲ ╱╱      ",
    "        ●        ",
    "      ╱╱ ╲╲      ",
    "    ╱╱     ╲╲    ",
    "  ╱╱         ╲╲  ",
    "●               ●",
]
