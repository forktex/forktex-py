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

"""Per-product ASCII/Unicode monograms.

Each glyph module exposes a single ``GLYPH: list[str]`` constant — raw,
uncoloured lines. Colour is applied at render time from
``branding.palette``. Keep glyphs as pure data: no imports, no logic. To
update a logo, edit the relevant ``glyphs/<product>.py`` and nothing else.

All glyphs share a 5-line × 9-column canvas so they can be laid out in a
row without manual padding. New products should match this canvas; if a
size change is genuinely needed, update every glyph in lockstep so
``render_row`` stays aligned.

Internal package — not part of the public Python API.
"""

__all__: list[str] = []
