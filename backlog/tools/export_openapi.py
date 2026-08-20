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

"""Export the grid app's OpenAPI schema to stdout.

The single source of truth for `make sync` codegen (TS RTK Query slices +
Python SDK). Schema generation does NOT need a database — the app object is
built without running startup, so no Postgres is touched.

Usage::

    python -m tools.export_openapi > openapi.json
"""

from __future__ import annotations

import json
import sys

from forktex.grid.app import build_app


def main() -> None:
    app = build_app()
    sys.stdout.write(json.dumps(app.openapi(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
