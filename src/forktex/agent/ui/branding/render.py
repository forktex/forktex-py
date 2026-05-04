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

"""Glyph → rich renderable.

Composition rules:
  - ``render_logo`` returns a coloured ``Text`` (just the art).
  - ``render_banner`` stacks the art above the product name.
  - ``render_row`` lays banners side-by-side via ``Columns``.

Callers never reach into ``glyphs/`` or ``palette`` directly — the public
surface lives on ``branding/__init__``. Adding a new product means:
  1. drop ``glyphs/<name>.py`` defining ``GLYPH``,
  2. add an entry to ``BRAND_PALETTE``,
  3. register it in ``_GLYPHS`` below.
"""

from __future__ import annotations

from rich.columns import Columns
from rich.console import Group
from rich.text import Text

from .glyphs import cloud as _cloud
from .glyphs import forktex as _forktex
from .glyphs import intelligence as _intelligence
from .glyphs import network as _network
from .palette import BRAND_PALETTE, Product

_GLYPHS: dict[Product, list[str]] = {
    "forktex": _forktex.GLYPH,
    "cloud": _cloud.GLYPH,
    "intelligence": _intelligence.GLYPH,
    "network": _network.GLYPH,
}


#: Characters in a glyph that are rendered as a dimmer halo of the brand
#: colour rather than the full colour. Used to soften tip-node surroundings.
#: Add new shade chars here if glyphs adopt richer block-character art.
_HALO_CHARS = frozenset("░")

#: Character substituted into empty (space) cells to create a faint
#: brand-coloured background field behind the wireframe. Set to ``None``
#: to disable backgrounds entirely; set to ``" "`` to keep cells empty.
_BACKGROUND_FILL: str | None = "·"


def render_logo(product: Product) -> Text:
    """Return the coloured monogram for *product*.

    Walks the glyph char-by-char applying three style tiers:
      - empty cells become the background fill char (dim brand colour)
      - ``_HALO_CHARS`` render as dim brand colour (tip-node halos)
      - everything else renders at full brand colour (arms, hub, nodes)

    Glyph files stay pure data — all rendering policy lives here.
    """
    color = BRAND_PALETTE[product]
    halo_style = f"{color} dim"
    lines = _GLYPHS[product]
    text = Text()
    for i, line in enumerate(lines):
        for ch in line:
            if ch == " " and _BACKGROUND_FILL is not None:
                text.append(_BACKGROUND_FILL, style=halo_style)
            elif ch in _HALO_CHARS:
                text.append(ch, style=halo_style)
            else:
                text.append(ch, style=color)
        if i < len(lines) - 1:
            text.append("\n")
    return text


def render_banner(product: Product, label: str | None = None) -> Group:
    """Return logo + bold product label, stacked vertically."""
    color = BRAND_PALETTE[product]
    name = (label or product).upper()
    return Group(
        render_logo(product),
        Text(name.center(len(_GLYPHS[product][0])), style=f"bold {color}"),
    )


def render_row(products: list[Product]) -> Columns:
    """Lay out banners side-by-side. Useful for ``forktex --version``."""
    return Columns(
        [render_banner(p) for p in products],
        padding=(0, 3),
        expand=False,
    )
