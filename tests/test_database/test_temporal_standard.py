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

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from forktex.database.models import AuditMixin, BaseDBModel, TimestampMixin, UtcDateTime


def _naive_temporal_columns(metadata: sa.MetaData) -> list[str]:
    offenders = []
    for table in metadata.tables.values():
        for col in table.columns:
            type_ = col.type
            if isinstance(type_, sa.DateTime) and not type_.timezone:
                offenders.append(f"{table.fullname}.{col.name}")
    return sorted(offenders)


def test_the_canonical_type_is_timezone_aware() -> None:
    assert isinstance(UtcDateTime, sa.TIMESTAMP)
    assert UtcDateTime.timezone is True


def test_a_bare_mapped_datetime_declares_a_tz_aware_column() -> None:

    class _ProbeBare(BaseDBModel):
        __tablename__ = "_probe_bare_datetime"
        id: Mapped[int] = mapped_column(primary_key=True)
        at: Mapped[datetime]

    assert _ProbeBare.__table__.c.at.type.timezone is True


def test_timestamp_and_audit_mixins_declare_tz_aware_columns() -> None:

    class _ProbeAudit(BaseDBModel, AuditMixin):
        __tablename__ = "_probe_audit_tz"
        id: Mapped[int] = mapped_column(primary_key=True)

    for name in ("created_at", "updated_at", "archived_at"):
        assert _ProbeAudit.__table__.c[name].type.timezone is True, name

    class _ProbeTs(BaseDBModel, TimestampMixin):
        __tablename__ = "_probe_ts_tz"
        id: Mapped[int] = mapped_column(primary_key=True)

    assert _naive_temporal_columns(_ProbeTs.metadata) == []


def test_no_declared_model_in_the_library_has_a_naive_temporal_column() -> None:
    assert _naive_temporal_columns(BaseDBModel.metadata) == []
