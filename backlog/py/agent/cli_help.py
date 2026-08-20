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

"""Root-CLI help taxonomy — the single source of truth for how ``forktex --help``
groups commands.

:data:`CATEGORIES` is a list of ``(label, names)`` pairs. The :class:`AsyncLazyGroup`
renderer reads it to print a ``make help``-style sectioned help: one named section
per category, each row in cyan-name (padded to :data:`NAME_COLUMN_WIDTH`) + the
short description. A command that isn't named in any category falls through to a
final ``Other`` section so the help never silently drops anything.

Adding / moving a top-level command is one edit here.
"""

from __future__ import annotations

#: Column width for the command-name slot, mirroring the awk template in
#: ``forktex.fsd.makefile`` (``%-22s``) that generates project Makefile help.
NAME_COLUMN_WIDTH = 22

#: Cyan + reset ANSI sequences, used only when the help formatter is rendering
#: to a colour-capable TTY. Inline-escape so :class:`asyncclick.HelpFormatter`
#: writes them verbatim.
ANSI_CYAN = "\033[36m"
ANSI_RESET = "\033[0m"

#: Ordered category map for ``forktex --help`` — the final 0.7.0 taxonomy.
#: Each tuple is ``(section label, [command names in render order])``. Adding
#: or moving a top-level command is one edit here.
#:
#: ``Core`` is the agentic identity (bare ``forktex`` plus the explicit verbs
#: every agentic session reaches for). ``Grounding`` is the substrate the agent
#: reads — three distinct stores under one mental model. ``Services`` are the
#: integration + verification + credential surfaces. ``Housekeeping`` is the
#: residual utility.
CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "Core",
        [
            "chat",
            "run",
            "plan",
        ],
    ),
    (
        "Grounding",
        [
            "knowledge",
            "arch",
        ],
    ),
    (
        "Services",
        [
            "cloud",
            "fsd",
            "auth",
            "serve",
        ],
    ),
    (
        "Housekeeping",
        [
            "clean",
        ],
    ),
]


def name_column_width(names: list[str]) -> int:
    """Return the actual name-column width for the rendered row set.

    Mirrors ``make help``'s ``%-22s`` cap: align to the longest name + a single
    space breathing room, but never wider than :data:`NAME_COLUMN_WIDTH`. Empty
    name lists collapse to 0 (the help section is then skipped).
    """
    if not names:
        return 0
    return min(NAME_COLUMN_WIDTH, max(len(name) for name in names) + 1)


__all__ = [
    "ANSI_CYAN",
    "ANSI_RESET",
    "CATEGORIES",
    "NAME_COLUMN_WIDTH",
    "name_column_width",
]
