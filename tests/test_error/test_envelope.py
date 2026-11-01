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
from pydantic import ValidationError

from forktex.error import (
    AppErrorCode,
    BadRequestError,
    ErrorEnvelope,
    NotFoundError,
    ServiceUnavailableError,
    TooManyRequestsError,
    UnauthorizedError,
    to_envelope,
)


def test_to_envelope_projects_apperror_fields() -> None:
    error = NotFoundError("user not found", details={"user_id": "abc"})
    envelope = to_envelope(error)

    assert envelope.code == AppErrorCode.NOT_FOUND
    assert envelope.message == "user not found"
    assert envelope.details == {"user_id": "abc"}


def test_to_envelope_handles_empty_details() -> None:
    error = UnauthorizedError("token expired")
    envelope = to_envelope(error)

    assert envelope.code == AppErrorCode.UNAUTHORIZED
    assert envelope.message == "token expired"
    assert envelope.details == {}


def test_envelope_emits_camel_case_keys() -> None:
    envelope = ErrorEnvelope(
        code=AppErrorCode.BAD_REQUEST,
        message="missing field",
        details={"field": "email"},
        trace_id="abc123",
    )
    dumped = envelope.model_dump(by_alias=True)
    assert dumped == {
        "code": "bad_request",
        "message": "missing field",
        "details": {"field": "email"},
        "traceId": "abc123",
    }


def test_to_envelope_carries_trace_id() -> None:
    envelope = to_envelope(NotFoundError("x"), trace_id="t-9")
    assert envelope.trace_id == "t-9"
    assert to_envelope(NotFoundError("x")).trace_id is None


def test_envelope_code_is_open_for_service_codes() -> None:
    env = ErrorEnvelope.model_validate({"code": "widget_locked", "message": "x", "details": {}})
    assert env.code == "widget_locked"
    assert to_envelope(NotFoundError("x")).code == "not_found" == AppErrorCode.NOT_FOUND


def test_too_many_requests_and_service_unavailable_round_trip_through_envelope() -> None:
    rate_limited = to_envelope(TooManyRequestsError("slow down"))
    assert rate_limited.code == AppErrorCode.RATE_LIMITED
    assert rate_limited.message == "slow down"

    unavailable = to_envelope(ServiceUnavailableError("maintenance window"))
    assert unavailable.code == AppErrorCode.UNAVAILABLE
    assert unavailable.message == "maintenance window"


def test_envelope_handles_non_ascii_message() -> None:
    error = BadRequestError("Ungültige Eingabe — 请检查输入")
    envelope = to_envelope(error)
    assert envelope.message == "Ungültige Eingabe — 请检查输入"
    dumped = envelope.model_dump(mode="json", by_alias=True)
    assert dumped["message"] == "Ungültige Eingabe — 请检查输入"


def test_envelope_validation_error_on_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"message": "x"})


def test_envelope_details_with_non_serializable_value_falls_back_to_str_in_json_mode() -> None:

    class Unserializable:
        def __str__(self) -> str:
            return "unserializable-repr"

    envelope = ErrorEnvelope(code="internal", message="x", details={"cause": Unserializable()})
    dumped = envelope.model_dump(mode="json")
    assert dumped["details"] == {"cause": "unserializable-repr"}


def test_envelope_details_normal_values_unaffected_by_fallback_serializer() -> None:
    envelope = ErrorEnvelope(code="internal", message="x", details={"user_id": "abc", "count": 3})
    assert envelope.model_dump(mode="json")["details"] == {"user_id": "abc", "count": 3}
