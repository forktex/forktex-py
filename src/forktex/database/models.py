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


import enum
import uuid
from datetime import datetime
from typing import Any, ClassVar

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.decl_api import declared_attr

from forktex.iso import to_iso


class ReprMixin:
    def __repr__(self) -> str:
        cls = self.__class__.__name__
        attrs = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items() if not k.startswith("_"))
        return f"{cls}({attrs})"


UtcDateTime = sa.TIMESTAMP(timezone=True)

_TYPE_ANNOTATION_MAP: dict[Any, Any] = {
    enum.StrEnum: sa.Enum(enum.StrEnum, native_enum=False, length=64),
    datetime: UtcDateTime,
}


class _EagerDefaults:
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    def __init_subclass__(cls, **kwargs: object) -> None:
        own_args = cls.__dict__.get("__mapper_args__")
        if isinstance(own_args, dict):
            cls.__mapper_args__ = {"eager_defaults": True, **own_args}
        super().__init_subclass__(**kwargs)


class BaseDBModel(_EagerDefaults, DeclarativeBase, ReprMixin):
    type_annotation_map: ClassVar[dict[Any, Any]] = _TYPE_ANNOTATION_MAP


def substrate_base(schema: str) -> type[DeclarativeBase]:

    class _SubstrateBase(_EagerDefaults, DeclarativeBase, ReprMixin):
        metadata = sa.MetaData(schema=schema)
        type_annotation_map: ClassVar[dict[Any, Any]] = _TYPE_ANNOTATION_MAP

    return _SubstrateBase


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class AuditMixin(TimestampMixin):
    __tablename__: ClassVar[str]
    __actor_fk_target__: ClassVar[str | None] = None

    @declared_attr
    def created_by_id(cls) -> Mapped[uuid.UUID | None]:
        fk_target = getattr(cls, "__actor_fk_target__", None)
        fk_args = [sa.ForeignKey(fk_target, ondelete="SET NULL")] if fk_target else []
        return mapped_column(sa.UUID(as_uuid=True), *fk_args, nullable=True, index=True)

    @declared_attr
    def updated_by_id(cls) -> Mapped[uuid.UUID | None]:
        fk_target = getattr(cls, "__actor_fk_target__", None)
        fk_args = [sa.ForeignKey(fk_target, ondelete="SET NULL")] if fk_target else []
        return mapped_column(sa.UUID(as_uuid=True), *fk_args, nullable=True, index=True)

    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True, index=True)

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        tablename = getattr(cls, "__tablename__", None)
        if not tablename:
            return
        if not issubclass(cls, DeclarativeBase):
            raise TypeError("AuditMixin can only be used with declarative model classes.")
        if not isinstance(tablename, str):
            raise TypeError("Classes using AuditMixin must define __tablename__ as a string")

    @declared_attr.directive
    def __table_args__(cls) -> tuple[sa.Index | sa.CheckConstraint, ...]:
        tablename = cls.__tablename__
        unique_fields = getattr(cls, "unique_fields", None)
        uniqueness = (_unique_among_active_rows(tablename, unique_fields),) if unique_fields else ()
        return (*uniqueness, _active_flag_matches_archived_at(tablename))


def _unique_among_active_rows(tablename: str, fields: list[str]) -> sa.Index:
    return sa.Index(
        f"uq_{tablename}_active",
        *fields,
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def _active_flag_matches_archived_at(tablename: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        "(is_active AND archived_at IS NULL) OR (NOT is_active AND archived_at IS NOT NULL)",
        name=f"ck_{tablename}_active_archive_consistency",
    )


class NamespacedMixin:
    namespace: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)


class JsonModelColumn[T: BaseModel]:
    @staticmethod
    def serialize(models: list[T] | list[dict]) -> list[dict]:
        result = []
        for v in models:
            if isinstance(v, BaseModel):
                result.append(v.model_dump(mode="json"))
            else:
                cleaned = {}
                for key, val in v.items():
                    if isinstance(val, enum.Enum):
                        cleaned[key] = val.value
                    elif isinstance(val, datetime):
                        cleaned[key] = to_iso(val)
                    else:
                        cleaned[key] = val
                result.append(cleaned)
        return result

    @staticmethod
    def deserialize(data: list[dict], model: type[T]) -> list[T]:
        return [model(**item) for item in (data or [])]


__all__ = [
    "AuditMixin",
    "BaseDBModel",
    "JsonModelColumn",
    "NamespacedMixin",
    "ReprMixin",
    "TimestampMixin",
    "UtcDateTime",
    "substrate_base",
]
