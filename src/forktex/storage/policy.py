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

from typing import Literal

from pydantic import ConfigDict, Field

from forktex.types import BaseValueObject

GET_OBJECT = "s3:GetObject"

type PresignMethod = Literal["get_object", "put_object"]

type PostCondition = dict[str, str] | list[object]


def object_arn(bucket: str, key_pattern: str = "*") -> str:
    return f"arn:aws:s3:::{bucket}/{key_pattern}"


class BucketPolicyPrincipal(BaseValueObject):
    model_config = ConfigDict(serialize_by_alias=True)

    aws: tuple[str, ...] = Field(default=("*",), serialization_alias="AWS")


class BucketPolicyStatement(BaseValueObject):
    model_config = ConfigDict(serialize_by_alias=True)

    action: tuple[str, ...] = Field(serialization_alias="Action")
    resource: tuple[str, ...] = Field(serialization_alias="Resource")
    effect: Literal["Allow", "Deny"] = Field(default="Allow", serialization_alias="Effect")
    principal: BucketPolicyPrincipal = Field(default_factory=BucketPolicyPrincipal, serialization_alias="Principal")


class BucketPolicy(BaseValueObject):
    """An S3 bucket policy. ``to_json()`` is what ``PutBucketPolicy`` takes."""

    model_config = ConfigDict(serialize_by_alias=True)

    statement: tuple[BucketPolicyStatement, ...] = Field(serialization_alias="Statement")
    version: Literal["2012-10-17"] = Field(default="2012-10-17", serialization_alias="Version")

    def to_json(self) -> str:
        return self.model_dump_json()


class PresignParams(BaseValueObject):
    """``generate_presigned_url``'s ``Params``. ``to_params()`` drops what is unset."""

    model_config = ConfigDict(serialize_by_alias=True)

    bucket: str = Field(serialization_alias="Bucket")
    key: str = Field(serialization_alias="Key")
    content_type: str | None = Field(default=None, serialization_alias="ContentType")
    response_content_disposition: str | None = Field(default=None, serialization_alias="ResponseContentDisposition")

    def to_params(self) -> dict[str, str]:
        return self.model_dump(exclude_none=True)


class PresignedPost(BaseValueObject):
    """A browser POST upload: send ``fields`` as form data to ``url``."""

    url: str
    fields: dict[str, str]


class PostPolicy(BaseValueObject):
    content_type: str | None = None
    max_size_bytes: int | None = None

    def fields(self) -> dict[str, str]:
        return {"Content-Type": self.content_type} if self.content_type else {}

    def conditions(self) -> list[PostCondition]:
        declared: list[PostCondition] = []
        if self.content_type:
            declared.append({"Content-Type": self.content_type})
        if self.max_size_bytes is not None:
            declared.append(["content-length-range", 1, self.max_size_bytes])
        return declared


def public_read_policy(bucket: str) -> BucketPolicy:
    return BucketPolicy(statement=(BucketPolicyStatement(action=(GET_OBJECT,), resource=(object_arn(bucket),)),))


__all__ = [
    "BucketPolicy",
    "BucketPolicyPrincipal",
    "BucketPolicyStatement",
    "PostPolicy",
    "PresignMethod",
    "PresignParams",
    "PresignedPost",
    "object_arn",
    "public_read_policy",
]
