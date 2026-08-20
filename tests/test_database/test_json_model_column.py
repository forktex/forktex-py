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


"""`JsonModelColumn` — the round-trip helper for JSON columns holding Pydantic models.

Exported from `forktex.database` and documented as the way to store a list of models
in a JSON column, but it had no test at all until the package moved: `serialize` is
where a `datetime` or an `Enum` silently becomes the wrong shape, and it is the half
that runs on the write path.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel

from forktex.database.models import JsonModelColumn


class _Colour(enum.StrEnum):
    red = "red"
    blue = "blue"


class _Tag(BaseModel):
    name: str
    weight: int


def test_serialize_pydantic_models_to_json_ready_dicts():
    out = JsonModelColumn.serialize([_Tag(name="a", weight=1), _Tag(name="b", weight=2)])
    assert out == [{"name": "a", "weight": 1}, {"name": "b", "weight": 2}]
    assert all(isinstance(d, dict) for d in out)


def test_serialize_accepts_plain_dicts_and_unwraps_enums():
    """A caller may hand over dicts rather than models; an `Enum` in one must come out
    as its *value*, or the column holds `<Colour.red: 'red'>` and fails to round-trip."""
    out = JsonModelColumn.serialize([{"colour": _Colour.red, "n": 1}])
    assert out == [{"colour": "red", "n": 1}]


def test_serialize_renders_datetimes_through_iso():
    """Temporal values go through `iso.to_iso`, so a JSON column never holds a
    `datetime` repr — and the text matches what the rest of the library writes."""
    at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    out = JsonModelColumn.serialize([{"at": at}])
    assert out == [{"at": "2026-01-01T12:00:00+00:00"}]


def test_serialize_passes_other_values_through_untouched():
    out = JsonModelColumn.serialize([{"s": "x", "n": 3, "f": 1.5, "b": True, "none": None, "l": [1, 2]}])
    assert out == [{"s": "x", "n": 3, "f": 1.5, "b": True, "none": None, "l": [1, 2]}]


def test_deserialize_rebuilds_models():
    tags = JsonModelColumn.deserialize([{"name": "a", "weight": 1}], _Tag)
    assert tags == [_Tag(name="a", weight=1)]
    assert isinstance(tags[0], _Tag)


def test_deserialize_treats_none_as_empty():
    """A JSON column defaults to NULL, so the read path must not blow up on it."""
    assert JsonModelColumn.deserialize(None, _Tag) == []  # type: ignore[arg-type]
    assert JsonModelColumn.deserialize([], _Tag) == []


def test_round_trip_is_lossless_for_model_lists():
    original = [_Tag(name="a", weight=1), _Tag(name="b", weight=2)]
    assert JsonModelColumn.deserialize(JsonModelColumn.serialize(original), _Tag) == original
