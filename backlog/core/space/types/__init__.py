# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of forktex-core.
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

"""Rich FieldType handlers shipped with the ``[space]`` extra.

There is no bare ``[grid]`` FILE handler to replace — core stays
storage-agnostic (see ``space/types/file.py``). Importing this module
registers the descriptor + lifecycle-hook ``file`` and ``vector``
handlers into ``grid``'s field-type registry as a side effect,
process-wide, making ``type_id: "file"`` and ``type_id: "vector"``
resolvable in a ``TableSpec``.

A consumer that wants a different handler for either ``type_id`` calls
``forktex_core.grid.register_field_type(handler, replace=True)``.
"""

# Side-effect imports: register the rich FILE + VECTOR handlers.
from forktex_core.space.types import file as _file  # noqa: F401
from forktex_core.space.types import vector as _vector  # noqa: F401

__all__: list[str] = []
