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

"""``forktex.agent.atoms`` — first-class catalog atoms as CLI commands.

Internal package. The factory ``register_atom_commands(cli)`` wires
every FSD atom from the bundled standard catalog as a top-level
``forktex <atom>`` Click command. Each command shells out to
``make <target>`` after resolving variants via
``forktex.fsd.variants.parse_atom_key``.

Bare ``forktex`` (no subcommand) keeps its existing behaviour: it
launches the runtime agent (chat REPL).
"""

from forktex.agent.atoms.dispatcher import (
    AtomDispatchError,
    dispatch_atom,
    register_atom_commands,
)

__all__ = ["AtomDispatchError", "dispatch_atom", "register_atom_commands"]
