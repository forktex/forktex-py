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

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from forktex.database.models import AuditMixin, BaseDBModel, substrate_base


def test_library_substrates_are_absent_from_the_consumer_registry() -> None:

    class _FlowLike(substrate_base("forktex_flow")):
        __tablename__ = "run"
        id: Mapped[int] = mapped_column(primary_key=True)

    class _GridLike(substrate_base("forktex_grid")):
        __tablename__ = "grid_row"
        id: Mapped[int] = mapped_column(primary_key=True)

    assert _FlowLike.__table__.schema == "forktex_flow"
    assert _GridLike.__table__.schema == "forktex_grid"
    leaked = [t.key for t in BaseDBModel.metadata.sorted_tables if t.schema in {"forktex_flow", "forktex_grid"}]
    assert leaked == [], f"library substrate tables leaked into the consumer registry: {leaked}"


def test_each_substrate_keeps_its_own_tables() -> None:

    class _A(substrate_base("substrate_a")):
        __tablename__ = "thing"
        id: Mapped[int] = mapped_column(primary_key=True)

    class _B(substrate_base("substrate_b")):
        __tablename__ = "thing"
        id: Mapped[int] = mapped_column(primary_key=True)

    assert _A.metadata is not _B.metadata
    assert {t.schema for t in _A.metadata.sorted_tables} == {"substrate_a"}
    assert {t.schema for t in _B.metadata.sorted_tables} == {"substrate_b"}


def test_substrate_base_defaults_the_schema_without_per_table_args() -> None:
    Base = substrate_base("some_substrate")

    class Thing(Base):
        __tablename__ = "thing"
        id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)

    assert Thing.__table__.schema == "some_substrate"


def test_substrate_base_inherits_the_shared_type_conventions() -> None:
    Base = substrate_base("some_substrate")
    assert Base.type_annotation_map == BaseDBModel.type_annotation_map


def test_audit_mixin_accepts_a_substrate_base() -> None:
    Base = substrate_base("some_substrate")

    class Audited(Base, AuditMixin):
        __tablename__ = "audited"
        id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)

    assert issubclass(Audited, DeclarativeBase)
    assert "archived_at" in Audited.__table__.c
