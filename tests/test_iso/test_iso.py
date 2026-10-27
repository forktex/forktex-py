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


from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from forktex.iso import from_date_iso, from_iso, now, to_date_iso, to_iso


def test_now_is_utc_aware() -> None:
    n = now()
    assert n.tzinfo is timezone.utc


def test_to_iso_naive_is_assumed_utc() -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert to_iso(naive) == "2026-01-01T12:00:00+00:00"


def test_to_iso_aware_converts_to_utc() -> None:
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    assert to_iso(aware) == "2026-01-01T10:00:00+00:00"


def test_to_iso_preserves_microseconds_only_when_present() -> None:
    assert to_iso(datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)) == "2026-01-01T12:00:00+00:00"
    assert to_iso(datetime(2026, 1, 1, 12, 0, 0, 500, tzinfo=timezone.utc)) == "2026-01-01T12:00:00.000500+00:00"


def test_to_iso_full_microsecond_precision() -> None:
    assert to_iso(datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)) == "2026-01-01T12:00:00.123456+00:00"


def test_to_iso_rejects_a_plain_date() -> None:
    with pytest.raises(TypeError, match="use to_date_iso"):
        to_iso(date(2026, 1, 1))


def test_from_iso_accepts_z_suffix() -> None:
    parsed = from_iso("2026-01-01T12:00:00Z")
    assert parsed == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_from_iso_naive_is_assumed_utc() -> None:
    parsed = from_iso("2026-01-01T12:00:00")
    assert parsed == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_from_iso_aware_converts_to_utc() -> None:
    parsed = from_iso("2026-01-01T12:00:00+02:00")
    assert parsed == datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_to_iso_strict_raises_on_naive_input() -> None:
    with pytest.raises(ValueError, match="naive"):
        to_iso(datetime(2026, 1, 1, 12, 0, 0), strict=True)


def test_to_iso_strict_accepts_aware_input() -> None:
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert to_iso(aware, strict=True) == "2026-01-01T12:00:00+00:00"


def test_to_iso_default_strict_false_unchanged() -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert to_iso(naive) == to_iso(naive, strict=False) == "2026-01-01T12:00:00+00:00"


def test_from_iso_strict_raises_on_naive_input() -> None:
    with pytest.raises(ValueError, match="offset"):
        from_iso("2026-01-01T12:00:00", strict=True)


def test_from_iso_strict_accepts_aware_input() -> None:
    parsed = from_iso("2026-01-01T12:00:00+02:00", strict=True)
    assert parsed == datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_from_iso_default_strict_false_unchanged() -> None:
    assert from_iso("2026-01-01T12:00:00") == from_iso("2026-01-01T12:00:00", strict=False)


def test_from_iso_malformed_string_raises_value_error() -> None:
    with pytest.raises(ValueError):
        from_iso("not-a-date")


def test_from_date_iso_malformed_string_raises_value_error() -> None:
    with pytest.raises(ValueError):
        from_date_iso("not-a-date")


def test_to_date_iso_accepts_a_full_datetime() -> None:
    assert to_date_iso(datetime(2026, 1, 1, 15, 30, 0)) == "2026-01-01"


def test_to_iso_from_iso_round_trip() -> None:
    n = now()
    assert from_iso(to_iso(n)) == n


def test_to_date_iso() -> None:
    assert to_date_iso(date(2026, 1, 1)) == "2026-01-01"


def test_from_date_iso() -> None:
    assert from_date_iso("2026-01-01") == date(2026, 1, 1)


def test_to_date_iso_from_date_iso_round_trip() -> None:
    d = date(2026, 6, 15)
    assert from_date_iso(to_date_iso(d)) == d


def test_to_iso_rejects_a_date_with_a_message_naming_the_right_function() -> None:
    with pytest.raises(TypeError, match="to_date_iso"):
        to_iso(date(2026, 1, 1))


def test_strict_mode_rejects_naive_and_offsetless_input() -> None:
    with pytest.raises(ValueError, match="naive"):
        to_iso(datetime(2026, 1, 1, 12, 0, 0), strict=True)

    with pytest.raises(ValueError, match="no UTC offset"):
        from_iso("2026-01-01T12:00:00", strict=True)

    assert to_iso(datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc), strict=True).endswith("+00:00")
    assert from_iso("2026-01-01T12:00:00+00:00", strict=True).tzinfo is not None
