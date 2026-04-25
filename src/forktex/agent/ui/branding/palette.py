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

"""Per-product accent colours.

Single source of truth — restyling the brand is a one-line edit here and
nothing else in the branding package changes. Values are rich-style
strings (named colours or ``#rrggbb`` hex). Modern terminals support
truecolor; older ones quantise to the nearest palette entry.

Hex values mirror the brand SVGs at ``cloud.forktex.com/assets/``:
  - cloud:        #44D62C  (green accent on the otherwise-black mark;
                            picked as the primary because pure black is
                            invisible on dark terminal backgrounds)
  - intelligence: #3853FF  (blue body)
  - network:      #1E3C72  (navy body — note: appears dim on dark
                            terminals; swap to the accent green
                            ``#4BAE4F`` if contrast is a problem)

Forktex itself has no SVG-defined accent (the mark is solid black), so
we reach for cyan to stay consistent with the existing CLI chrome.
"""

from __future__ import annotations

from typing import Literal

Product = Literal["forktex", "cloud", "intelligence", "network"]

BRAND_PALETTE: dict[Product, str] = {
    "forktex": "cyan",
    "cloud": "#44D62C",
    "intelligence": "#3853FF",
    "network": "#1E3C72",
}
