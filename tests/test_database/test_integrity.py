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

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from forktex.database.integrity import (
    SQLSTATE_CHECK_VIOLATION,
    SQLSTATE_FOREIGN_KEY_VIOLATION,
    SQLSTATE_NOT_NULL_VIOLATION,
    SQLSTATE_UNIQUE_VIOLATION,
    integrity_boundary,
    read_boundary,
)
from forktex.error import AlreadyExistsError, BadRequestError


class _Orig(Exception):
    def __init__(self, sqlstate: str | None, message: str = "driver detail") -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


def _integrity_error(sqlstate: str | None, message: str = "driver detail") -> IntegrityError:
    return IntegrityError("INSERT ...", {}, _Orig(sqlstate, message))


@pytest.mark.asyncio
async def test_unique_violation_becomes_already_exists() -> None:
    with pytest.raises(AlreadyExistsError) as exc_info:
        async with integrity_boundary():
            raise _integrity_error(SQLSTATE_UNIQUE_VIOLATION)
    assert exc_info.value.code == "already_exists"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sqlstate",
    [SQLSTATE_FOREIGN_KEY_VIOLATION, SQLSTATE_NOT_NULL_VIOLATION, SQLSTATE_CHECK_VIOLATION],
)
async def test_other_constraint_violations_become_bad_request(sqlstate: str) -> None:
    with pytest.raises(BadRequestError):
        async with integrity_boundary():
            raise _integrity_error(sqlstate)


@pytest.mark.asyncio
async def test_driver_message_is_not_leaked_into_the_user_facing_error() -> None:
    secret = "user@example.com already registered"
    with pytest.raises(AlreadyExistsError) as exc_info:
        async with integrity_boundary():
            raise _integrity_error(SQLSTATE_UNIQUE_VIOLATION, secret)
    assert secret not in str(exc_info.value)
    assert exc_info.value.message == "resource already exists"
    assert isinstance(exc_info.value.__cause__, IntegrityError)


@pytest.mark.asyncio
async def test_missing_sqlstate_falls_back_to_the_substring_heuristic() -> None:
    with pytest.raises(AlreadyExistsError):
        async with integrity_boundary():
            raise _integrity_error(None, "duplicate key value violates unique constraint")

    with pytest.raises(BadRequestError):
        async with integrity_boundary():
            raise _integrity_error(None, "some other constraint problem")


@pytest.mark.asyncio
async def test_non_integrity_exceptions_pass_through_untouched() -> None:
    with pytest.raises(ValueError, match="unrelated"):
        async with integrity_boundary():
            raise ValueError("unrelated")


@pytest.mark.asyncio
async def test_read_boundary_maps_data_exceptions_only() -> None:
    with pytest.raises(BadRequestError):
        async with read_boundary():
            raise DBAPIError("SELECT ...", {}, _Orig("22P02"))

    with pytest.raises(DBAPIError):
        async with read_boundary():
            raise DBAPIError("SELECT ...", {}, _Orig("42P01"))
