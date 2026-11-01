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


import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from forktex.database import BaseDBModel, TimestampMixin, AuditMixin, NamespacedMixin, substrate_base


class _Audited(BaseDBModel, AuditMixin):
    __tablename__ = "mixin_audited"
    unique_fields = ("slug",)

    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid7)
    slug: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class _Timestamped(BaseDBModel, TimestampMixin):
    __tablename__ = "mixin_timestamped"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    value: Mapped[str] = mapped_column(sa.String(50))


class _Namespaced(BaseDBModel, NamespacedMixin, TimestampMixin):
    __tablename__ = "mixin_namespaced"
    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(sa.String(100))


@pytest.mark.asyncio
async def test_timestamp_mixin_sets_created_at(models_session: AsyncSession) -> None:
    row = _Timestamped(value="hello")
    models_session.add(row)
    await models_session.flush()
    assert row.created_at is not None
    assert row.updated_at is not None


@pytest.mark.asyncio
async def test_timestamp_mixin_updated_at_changes_on_update(models_session: AsyncSession) -> None:
    row = _Timestamped(value="v1")
    models_session.add(row)
    await models_session.commit()
    original_updated = row.updated_at

    row.value = "v2"
    await models_session.commit()
    assert row.updated_at > original_updated


@pytest.mark.asyncio
async def test_audit_mixin_defaults(models_session: AsyncSession) -> None:
    row = _Audited(slug="alpha")
    models_session.add(row)
    await models_session.flush()
    assert row.is_active is True
    assert row.archived_at is None
    assert row.created_by_id is None
    assert row.updated_by_id is None
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_audit_mixin_with_actor_ids(models_session: AsyncSession) -> None:
    actor = uuid.uuid7()
    row = _Audited(slug="beta", created_by_id=actor, updated_by_id=actor)
    models_session.add(row)
    await models_session.flush()
    await models_session.refresh(row)
    assert row.created_by_id == actor
    assert row.updated_by_id == actor


@pytest.mark.asyncio
async def test_audit_mixin_soft_delete(models_session: AsyncSession) -> None:
    row = _Audited(slug="gamma")
    models_session.add(row)
    await models_session.flush()

    now = datetime.now(timezone.utc)
    row.archived_at = now
    row.is_active = False
    await models_session.commit()
    await models_session.refresh(row)
    assert row.is_active is False
    assert row.archived_at is not None


@pytest.mark.asyncio
async def test_audit_check_constraint_active_and_archived_raises(models_session: AsyncSession) -> None:
    row = _Audited(slug="bad-state")
    models_session.add(row)
    await models_session.flush()
    row.archived_at = datetime.now(timezone.utc)
    row.is_active = True
    with pytest.raises(IntegrityError):
        await models_session.flush()


@pytest.mark.asyncio
async def test_audit_check_constraint_inactive_without_archived_at_raises(models_session: AsyncSession) -> None:
    row = _Audited(slug="bad-state-2", is_active=False, archived_at=None)
    models_session.add(row)
    with pytest.raises(IntegrityError):
        await models_session.flush()


@pytest.mark.asyncio
async def test_partial_unique_active_rows_rejects_duplicate(models_session: AsyncSession) -> None:
    models_session.add(_Audited(slug="dup"))
    await models_session.flush()
    models_session.add(_Audited(slug="dup"))
    with pytest.raises(IntegrityError):
        await models_session.flush()


@pytest.mark.asyncio
async def test_partial_unique_allows_duplicate_after_archive(models_session: AsyncSession) -> None:
    row = _Audited(slug="reuse")
    models_session.add(row)
    await models_session.flush()
    row.archived_at = datetime.now(timezone.utc)
    row.is_active = False
    await models_session.commit()

    models_session.add(_Audited(slug="reuse"))
    await models_session.flush()


@pytest.mark.asyncio
async def test_partial_unique_allows_multiple_archived_rows(models_session: AsyncSession) -> None:
    for _ in range(3):
        row = _Audited(slug="archived-many")
        models_session.add(row)
        await models_session.flush()
        row.archived_at = datetime.now(timezone.utc)
        row.is_active = False
        await models_session.commit()

    stored = await models_session.scalar(
        sa.select(sa.func.count()).select_from(_Audited.__table__).where(_Audited.slug == "archived-many")
    )
    assert stored == 3


def test_audit_mixin_requires_a_declarative_model() -> None:
    with pytest.raises(TypeError, match="declarative"):

        class Bad(AuditMixin):
            __tablename__ = "bad"


def test_audit_mixin_actor_fk_target_inherited_by_subclasses() -> None:

    class ServiceMixin(AuditMixin):
        __actor_fk_target__ = "user.id"

    class _Row(substrate_base("actor_fk_probe"), ServiceMixin):
        __tablename__ = "row"
        id: Mapped[int] = mapped_column(primary_key=True)

    for column in ("created_by_id", "updated_by_id"):
        (fk,) = _Row.__table__.c[column].foreign_keys
        assert fk.target_fullname == "user.id"
        assert fk.ondelete == "SET NULL"


@pytest.mark.asyncio
async def test_namespaced_mixin_stores_namespace(models_session: AsyncSession) -> None:
    row = _Namespaced(namespace="org-abc-123", name="widget")
    models_session.add(row)
    await models_session.flush()
    await models_session.refresh(row)
    assert row.namespace == "org-abc-123"


@pytest.mark.asyncio
async def test_namespaced_mixin_no_fk_constraint(models_session: AsyncSession) -> None:
    row = _Namespaced(namespace="nonexistent-tenant", name="item")
    models_session.add(row)
    await models_session.flush()


@pytest.mark.asyncio
async def test_namespaced_mixin_different_namespaces_same_name(models_session: AsyncSession) -> None:
    models_session.add(_Namespaced(namespace="org-1", name="shared-name"))
    models_session.add(_Namespaced(namespace="org-2", name="shared-name"))
    await models_session.flush()


@pytest.mark.asyncio
async def test_updated_at_is_readable_after_an_update_without_refresh(models_session: AsyncSession) -> None:
    row = _Timestamped(value="v1")
    models_session.add(row)
    await models_session.flush()
    created = row.updated_at

    row.value = "v2"
    await models_session.flush()
    assert row.updated_at >= created


class _Party(BaseDBModel, TimestampMixin):
    __tablename__ = "mixin_polymorphic_party"
    __mapper_args__ = {"polymorphic_on": "kind", "polymorphic_identity": "party"}

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(20))
    value: Mapped[str] = mapped_column(sa.String(20))


class _Company(_Party):
    __mapper_args__ = {"polymorphic_identity": "company"}


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [_Party, _Company])
async def test_own_mapper_args_keep_updated_at_readable(models_session: AsyncSession, model: type[_Party]) -> None:
    row = model(value="v1")
    models_session.add(row)
    await models_session.flush()
    created = row.updated_at

    row.value = "v2"
    await models_session.flush()
    assert row.updated_at >= created
    assert sa.inspect(model).polymorphic_identity == model.__mapper_args__["polymorphic_identity"]


class _ArgsFromMixin:
    """`__mapper_args__` on a mixin, not on the model itself."""

    __mapper_args__: ClassVar[dict[str, Any]] = {"confirm_deleted_rows": False}


class _InheritedArgs(_ArgsFromMixin, BaseDBModel):
    __tablename__ = "eager_inherited_args"

    id: Mapped[int] = mapped_column(primary_key=True)


class _DeclaredArgs(BaseDBModel):
    __tablename__ = "eager_declared_args"

    id: Mapped[int] = mapped_column(primary_key=True)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:  # noqa: N805
        return {"confirm_deleted_rows": False}


@pytest.mark.parametrize("model", [_InheritedArgs, _DeclaredArgs], ids=["from a mixin", "from declared_attr"])
def test_eager_defaults_survives_mapper_args_the_model_does_not_own(model: type[BaseDBModel]) -> None:
    """The merge read `cls.__dict__`, so `__mapper_args__` arriving from a mixin
    or a `@declared_attr.directive` silently dropped `eager_defaults` -- and a
    model with its own mapper args is exactly where reading `updated_at` after
    an update raises MissingGreenlet."""
    assert sa.inspect(model).eager_defaults is True
    assert sa.inspect(model).confirm_deleted_rows is False


class _PolyRoot(BaseDBModel):
    __tablename__ = "eager_poly_root"
    __mapper_args__: ClassVar[dict[str, Any]] = {
        "polymorphic_identity": "root",
        "polymorphic_on": "kind",
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(20))


class _PolyBranch(_PolyRoot):
    __mapper_args__: ClassVar[dict[str, Any]] = {"polymorphic_identity": "branch"}


class _PolyLeaf(_PolyBranch):
    """Declares nothing — it must not inherit its parent's identity."""


def test_a_subclass_does_not_steal_its_mapped_parents_polymorphic_identity() -> None:
    """The eager_defaults merge walked the whole MRO, so a leaf that declared no
    `__mapper_args__` copied its mapped parent's dict -- identity included --
    and SQLAlchemy reassigned 'branch' to the leaf. A row written as the parent
    then loaded back as the leaf."""
    assert sa.inspect(_PolyBranch).polymorphic_identity == "branch"
    assert sa.inspect(_PolyLeaf).polymorphic_identity != "branch"

    # and the merge still has to do its job on every level
    assert sa.inspect(_PolyRoot).eager_defaults is True
    assert sa.inspect(_PolyBranch).eager_defaults is True
    assert sa.inspect(_PolyLeaf).eager_defaults is True
