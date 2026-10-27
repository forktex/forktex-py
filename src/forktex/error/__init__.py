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

from enum import StrEnum
from typing import Any

from pydantic import Field, field_serializer
from pydantic_core import to_jsonable_python

from forktex.types import BaseAppModel


class AppErrorCode(StrEnum):
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    BAD_REQUEST = "bad_request"
    VALIDATION = "validation"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERNAL = "internal"


class AppError(Exception):
    code: AppErrorCode = AppErrorCode.INTERNAL

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    code = AppErrorCode.NOT_FOUND


class AlreadyExistsError(AppError):
    code = AppErrorCode.ALREADY_EXISTS


class BadRequestError(AppError):
    code = AppErrorCode.BAD_REQUEST


class UnprocessableEntityError(AppError):
    code = AppErrorCode.VALIDATION


class UnauthorizedError(AppError):
    code = AppErrorCode.UNAUTHORIZED


class ForbiddenError(AppError):
    code = AppErrorCode.FORBIDDEN


class ConflictError(AppError):
    code = AppErrorCode.CONFLICT


class TooManyRequestsError(AppError):
    code = AppErrorCode.RATE_LIMITED


class ServiceUnavailableError(AppError):
    code = AppErrorCode.UNAVAILABLE


class ErrorEnvelope(BaseAppModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None

    @field_serializer("details", when_used="json")
    def _serialize_details(self, value: dict[str, Any]) -> dict[str, Any]:
        return to_jsonable_python(value, fallback=str)


def to_envelope(error: AppError, *, trace_id: str | None = None) -> ErrorEnvelope:
    return ErrorEnvelope(code=str(error.code), message=error.message, details=error.details, trace_id=trace_id)


__all__ = [
    "AlreadyExistsError",
    "AppError",
    "AppErrorCode",
    "BadRequestError",
    "ConflictError",
    "ErrorEnvelope",
    "ForbiddenError",
    "NotFoundError",
    "ServiceUnavailableError",
    "TooManyRequestsError",
    "UnauthorizedError",
    "UnprocessableEntityError",
    "to_envelope",
]
