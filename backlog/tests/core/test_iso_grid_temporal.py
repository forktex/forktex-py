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


"""Grid temporal-normalization guards, split out of tests/test_iso/test_iso.py.

These assert grid's DateTimeType/DateType normalize output, not iso's own
behaviour — they moved here when grid went to backlog. Fold them back into
the iso suite (or grid's own) when grid returns.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def test_grid_datetime_normalize_output_unchanged():
    """Regression guard: grid's DateTimeType.normalize relocated its UTC
    normalization into to_iso() — the stored/indexed text must not change."""
    from forktex.grid.domain.fieldtypes.base import EmptyConfig
    from forktex.grid.domain.fieldtypes.temporal import DateTimeType

    handler = DateTimeType()
    config = EmptyConfig()
    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    assert handler.normalize(naive, config=config) == "2026-01-01T12:00:00+00:00"
    assert handler.normalize(aware, config=config) == "2026-01-01T07:00:00+00:00"
    assert handler.normalize("2026-01-01T12:00:00+00:00", config=config) == "2026-01-01T12:00:00+00:00"


def test_grid_date_normalize_output_unchanged():
    from forktex.grid.domain.fieldtypes.base import EmptyConfig
    from forktex.grid.domain.fieldtypes.temporal import DateType

    handler = DateType()
    config = EmptyConfig()
    assert handler.normalize(date(2026, 1, 1), config=config) == "2026-01-01"
    assert handler.normalize(datetime(2026, 1, 1, 12, 0, 0), config=config) == "2026-01-01"
