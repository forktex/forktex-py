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

from datetime import UTC, date, datetime


def now() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime, *, strict: bool = False) -> str:
    if not isinstance(value, datetime):
        raise TypeError(f"{value!r} is not a datetime — use to_date_iso() for date values")
    if value.tzinfo is None:
        if strict:
            raise ValueError(f"{value!r} is a naive datetime — pass an aware one, or strict=False")
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def from_iso(value: str, *, strict: bool = False) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        if strict:
            raise ValueError(f"{value!r} has no UTC offset — pass an offset, or strict=False")
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def to_date_iso(value: date) -> str:
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat()


def from_date_iso(value: str) -> date:
    return date.fromisoformat(value)


__all__ = ["from_date_iso", "from_iso", "now", "to_date_iso", "to_iso"]
