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

import json

import pytest

from forktex.storage import (
    BucketPolicy,
    BucketPolicyStatement,
    PostPolicy,
    PresignParams,
    object_arn,
    public_read_policy,
)


def test_the_public_read_policy_is_the_document_s3_expects() -> None:
    """The policy used to be a dict literal inlined in `ensure_bucket` and
    `json.dumps`-ed, so nothing pinned the document actually sent to S3."""
    document = json.loads(public_read_policy("media").to_json())

    assert document == {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": ["arn:aws:s3:::media/*"],
            }
        ],
    }


def test_an_object_arn_covers_the_whole_bucket_by_default() -> None:
    assert object_arn("media") == "arn:aws:s3:::media/*"
    assert object_arn("media", "invoices/*") == "arn:aws:s3:::media/invoices/*"


def test_a_policy_is_frozen_so_a_grant_cannot_be_widened_after_review() -> None:
    policy = public_read_policy("media")
    with pytest.raises(ValueError):
        policy.statement = ()


def test_a_deny_statement_serialises_under_its_aws_names() -> None:
    policy = BucketPolicy(
        statement=(
            BucketPolicyStatement(
                action=("s3:DeleteObject",),
                resource=(object_arn("media", "locked/*"),),
                effect="Deny",
            ),
        )
    )
    assert json.loads(policy.to_json())["Statement"][0]["Effect"] == "Deny"


@pytest.mark.parametrize(
    ("policy", "fields", "conditions"),
    [
        (PostPolicy(), {}, []),
        (
            PostPolicy(content_type="image/png"),
            {"Content-Type": "image/png"},
            [{"Content-Type": "image/png"}],
        ),
        (PostPolicy(max_size_bytes=1024), {}, [["content-length-range", 1, 1024]]),
    ],
    ids=["empty", "content type", "size cap"],
)
def test_a_post_policy_declares_only_what_it_was_given(
    policy: PostPolicy, fields: dict[str, str], conditions: list[object]
) -> None:
    assert policy.fields() == fields
    assert policy.conditions() == conditions


def test_presign_params_omit_what_is_unset() -> None:
    """They were a dict mutated by two `if`s, so an unset value could reach S3."""
    assert PresignParams(bucket="b", key="k").to_params() == {"Bucket": "b", "Key": "k"}
    assert PresignParams(bucket="b", key="k", content_type="text/plain").to_params() == {
        "Bucket": "b",
        "Key": "k",
        "ContentType": "text/plain",
    }
