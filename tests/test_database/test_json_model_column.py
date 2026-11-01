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


def test_serialize_pydantic_models_to_json_ready_dicts() -> None:
    out = JsonModelColumn.serialize([_Tag(name="a", weight=1), _Tag(name="b", weight=2)])
    assert out == [{"name": "a", "weight": 1}, {"name": "b", "weight": 2}]


def test_serialize_accepts_plain_dicts_and_unwraps_enums() -> None:
    out = JsonModelColumn.serialize([{"colour": _Colour.red, "n": 1}])
    assert out == [{"colour": "red", "n": 1}]


def test_serialize_renders_datetimes_through_iso() -> None:
    at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    out = JsonModelColumn.serialize([{"at": at}])
    assert out == [{"at": "2026-01-01T12:00:00+00:00"}]


def test_serialize_passes_other_values_through_untouched() -> None:
    out = JsonModelColumn.serialize([{"s": "x", "n": 3, "f": 1.5, "b": True, "none": None, "l": [1, 2]}])
    assert out == [{"s": "x", "n": 3, "f": 1.5, "b": True, "none": None, "l": [1, 2]}]


def test_deserialize_rebuilds_models() -> None:
    tags = JsonModelColumn.deserialize([{"name": "a", "weight": 1}], _Tag)
    assert tags == [_Tag(name="a", weight=1)]


def test_deserialize_treats_none_as_empty() -> None:
    assert JsonModelColumn.deserialize(None, _Tag) == []
    assert JsonModelColumn.deserialize([], _Tag) == []


def test_round_trip_is_lossless_for_model_lists() -> None:
    original = [_Tag(name="a", weight=1), _Tag(name="b", weight=2)]
    assert JsonModelColumn.deserialize(JsonModelColumn.serialize(original), _Tag) == original
