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

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel

from forktex.iso import to_date_iso, to_iso

type JsonScalar = str | int | float | bool | None

type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

type JsonObject = dict[str, JsonValue]

UtcDateTime = Annotated[datetime, PlainSerializer(to_iso, return_type=str)]
"""Datetime field type for ``BaseAppModel``/``BaseWireValueObject`` subclasses.

Pydantic's default ``datetime`` serialization emits a ``Z``-suffixed,
non-UTC-forced, offset-preserving string — it disagrees with every other
timestamp `forktex` produces (``log``'s JSON, ``grid``'s stored text,
``flow``'s cursors, ``database``'s JSON columns), all of which go through
``forktex.iso.to_iso()``. Use ``UtcDateTime`` instead of a plain
``datetime`` annotation on any wire-facing model field to get the same
canonical UTC text everywhere::

    class Invoice(BaseAppModel):
        created_at: UtcDateTime
"""

UtcDate = Annotated[date, PlainSerializer(to_date_iso, return_type=str)]
"""Date field type for ``BaseAppModel``/``BaseWireValueObject`` subclasses —
the ``date``-only counterpart of ``UtcDateTime``. Plain ``date`` fields
already serialize as ``YYYY-MM-DD`` by default in Pydantic (there's no
timezone/offset ambiguity to normalize the way there is for ``datetime``,
and Pydantic's own validator already rejects a ``datetime`` with a nonzero
time component passed where a ``date`` is expected), so ``UtcDate`` exists
for naming symmetry and consistency with ``UtcDateTime`` rather than to
fix a live bug::

    class Invoice(BaseAppModel):
        due_date: UtcDate
"""


class BaseAppModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


class BaseValueObject(BaseModel):
    model_config = ConfigDict(frozen=True)


class BaseWireValueObject(BaseValueObject):
    model_config = ConfigDict(
        frozen=True,
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


__all__ = [
    "BaseAppModel",
    "BaseValueObject",
    "BaseWireValueObject",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "UtcDate",
    "UtcDateTime",
]
