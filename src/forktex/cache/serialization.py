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

"""Pydantic-aware JSON serialization for cache values."""

from __future__ import annotations

import json
from typing import overload

from pydantic import BaseModel

from forktex.types import JsonValue


def serialize(value: object) -> str:
    """Serialize a value to JSON string. Handles Pydantic models."""
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    return json.dumps(value, default=str)


@overload
def deserialize[T: BaseModel](data: str, model: type[T]) -> T: ...


@overload
def deserialize(data: str, model: None) -> JsonValue: ...


def deserialize[T: BaseModel](data: str, model: type[T] | None) -> T | JsonValue:
    """Deserialize a JSON string, optionally into a Pydantic model.

    Overloaded rather than returning ``object``: the single signature declared a
    type parameter and then discarded it, so ``deserialize(raw, UserProfile)``
    type-checked as ``object``. That erasure propagated through ``fetch_or_set``
    and ``fetch_swr`` into ``@cached``, which is why ``response_model=`` gave a
    consumer no type information at all.
    """
    if model:
        return model.model_validate_json(data)
    return json.loads(data)


__all__ = ["deserialize", "serialize"]
