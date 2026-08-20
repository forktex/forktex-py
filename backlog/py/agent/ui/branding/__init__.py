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

"""Brand glyphs for the forktex CLI.

Public surface:
    render_logo(product)   -> rich.text.Text
    render_banner(product) -> rich.console.Group   # logo + label
    render_row(products)   -> rich.columns.Columns # side-by-side banners
    BRAND_PALETTE          -> {product: rich-style colour}
    Product                -> Literal type alias

Layout — each concern lives in its own file so updates are isolated:

    branding/
      palette.py        ← colours per product (one-line edits)
      render.py         ← glyph → rich renderable (rarely changes)
      glyphs/
        forktex.py      ← pure data: list[str]
        cloud.py
        intelligence.py
        network.py

Adding a 5th product is three small edits (palette + new glyph file +
register in render._GLYPHS); no other code changes anywhere.
"""

from .palette import BRAND_PALETTE, Product
from .render import render_banner, render_logo, render_row

__all__ = [
    "BRAND_PALETTE",
    "Product",
    "render_banner",
    "render_logo",
    "render_row",
]
