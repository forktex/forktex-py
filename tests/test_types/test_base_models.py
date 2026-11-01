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
from pydantic import ValidationError

from forktex.types import BaseAppModel, BaseValueObject, BaseWireValueObject, UtcDate, UtcDateTime


def test_base_app_model_camel_alias() -> None:
    class Person(BaseAppModel):
        first_name: str
        last_name: str

    p = Person(first_name="Ada", last_name="Lovelace")
    assert p.model_dump(by_alias=True) == {"firstName": "Ada", "lastName": "Lovelace"}
    assert Person.model_validate({"firstName": "Ada", "lastName": "L"}).first_name == "Ada"
    assert Person.model_validate({"first_name": "Ada", "last_name": "L"}).first_name == "Ada"


def test_value_object_is_frozen() -> None:
    class Currency(BaseValueObject):
        amount: int
        code: str

    eur = Currency(amount=100, code="EUR")
    with pytest.raises(ValidationError):
        eur.amount = 200


def test_value_object_equality_is_structural() -> None:
    class Currency(BaseValueObject):
        amount: int
        code: str

    a = Currency(amount=100, code="EUR")
    b = Currency(amount=100, code="EUR")
    c = Currency(amount=200, code="EUR")
    assert a == b
    assert a != c
    assert {a, b, c} == {a, c}


def test_wire_value_object_combines_both() -> None:
    class Money(BaseWireValueObject):
        amount_cents: int
        currency_code: str

    m = Money(amount_cents=1000, currency_code="USD")
    with pytest.raises(ValidationError):
        m.amount_cents = 2000
    assert m.model_dump(by_alias=True) == {"amountCents": 1000, "currencyCode": "USD"}
    assert Money.model_validate({"amountCents": 1000, "currencyCode": "USD"}).amount_cents == 1000
    assert Money.model_validate({"amount_cents": 1000, "currency_code": "USD"}).amount_cents == 1000


def test_utc_datetime_forces_utc_unlike_plain_datetime_field() -> None:

    class Event(BaseAppModel):
        canonical_at: UtcDateTime
        plain_at: datetime

    aware_non_utc = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    dumped = Event(canonical_at=aware_non_utc, plain_at=aware_non_utc).model_dump(mode="json", by_alias=True)
    assert dumped["canonicalAt"] == "2026-01-01T07:00:00+00:00"
    assert dumped["plainAt"] == "2026-01-01T12:00:00+05:00"


def test_utc_datetime_forces_utc_for_naive_input() -> None:
    class Event(BaseAppModel):
        canonical_at: UtcDateTime
        plain_at: datetime

    naive = datetime(2026, 1, 1, 12, 0, 0)
    dumped = Event(canonical_at=naive, plain_at=naive).model_dump(mode="json", by_alias=True)
    assert dumped["canonicalAt"] == "2026-01-01T12:00:00+00:00"
    assert dumped["plainAt"] == "2026-01-01T12:00:00"


def test_nested_base_app_model() -> None:
    class Address(BaseAppModel):
        street_name: str

    class Person(BaseAppModel):
        first_name: str
        home_address: Address

    p = Person(first_name="Ada", home_address=Address(street_name="Main St"))
    assert p.model_dump(by_alias=True) == {
        "firstName": "Ada",
        "homeAddress": {"streetName": "Main St"},
    }
    parsed = Person.model_validate({"firstName": "Ada", "homeAddress": {"street_name": "Main St"}})
    assert parsed.home_address.street_name == "Main St"


def test_base_app_model_validation_error_on_missing_required_field() -> None:
    class Person(BaseAppModel):
        first_name: str

    with pytest.raises(ValidationError):
        Person.model_validate({})


def test_optional_utc_datetime_field() -> None:
    class Event(BaseAppModel):
        canonical_at: UtcDateTime | None = None

    assert Event().model_dump(mode="json", by_alias=True) == {"canonicalAt": None}

    naive = datetime(2026, 1, 1, 12, 0, 0)
    dumped = Event(canonical_at=naive).model_dump(mode="json", by_alias=True)
    assert dumped["canonicalAt"] == "2026-01-01T12:00:00+00:00"


def test_utc_datetime_on_base_value_object() -> None:

    class Snapshot(BaseValueObject):
        canonical_at: UtcDateTime

    aware_non_utc = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    dumped = Snapshot(canonical_at=aware_non_utc).model_dump(mode="json")
    assert dumped["canonical_at"] == "2026-01-01T07:00:00+00:00"


def test_utc_datetime_validated_from_string_keeps_original_offset_until_serialized() -> None:

    class Event(BaseAppModel):
        canonical_at: UtcDateTime

    parsed = Event.model_validate({"canonicalAt": "2026-01-01T12:00:00+05:00"})
    assert parsed.canonical_at.utcoffset() == timedelta(hours=5)
    dumped = parsed.model_dump(mode="json", by_alias=True)
    assert dumped["canonicalAt"] == "2026-01-01T07:00:00+00:00"


def test_utc_date_field() -> None:
    class Invoice(BaseAppModel):
        due_date: UtcDate

    assert Invoice(due_date=date(2026, 1, 1)).model_dump(mode="json", by_alias=True) == {"dueDate": "2026-01-01"}
    zero_time = Invoice(due_date=datetime(2026, 1, 1, 0, 0, 0)).model_dump(mode="json", by_alias=True)
    assert zero_time == {"dueDate": "2026-01-01"}
    with pytest.raises(ValidationError):
        Invoice(due_date=datetime(2026, 1, 1, 15, 30, 0))


def test_base_value_object_rejects_camel_case_input() -> None:

    class Money(BaseValueObject):
        amount_cents: int

    with pytest.raises(ValidationError):
        Money.model_validate({"amountCents": 100})
    assert Money.model_validate({"amount_cents": 100}).amount_cents == 100
