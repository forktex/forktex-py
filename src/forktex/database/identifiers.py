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

import re

from forktex.error import BadRequestError

MAX_IDENT = 128

IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

SLUG_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]*$")

SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def validate_identifier(name: str, what: str = "identifier") -> None:
    if not name or len(name) > MAX_IDENT or not IDENT_RE.match(name):
        raise BadRequestError(f"invalid {what} {name!r}: must be a plain SQL identifier (≤{MAX_IDENT} chars)")


def validate_slug(slug: str) -> None:
    if not slug or len(slug) > MAX_IDENT or not SLUG_RE.match(slug):
        raise BadRequestError(f"invalid slug {slug!r}: must be alphanumeric/_/- (≤{MAX_IDENT} chars)")


def validate_schema(schema: str) -> None:
    if not schema or len(schema) > MAX_IDENT or not SCHEMA_RE.match(schema):
        raise BadRequestError(f"unsafe schema name: {schema!r}")


def validate_relation(relation: str) -> None:
    parts = relation.split(".")
    if len(parts) not in (1, 2) or not all(p and len(p) <= MAX_IDENT and IDENT_RE.match(p) for p in parts):
        raise BadRequestError(f"unsafe relation reference: {relation!r}")


def is_identifier(name: str) -> bool:
    return bool(name) and len(name) <= MAX_IDENT and IDENT_RE.match(name) is not None


__all__ = [
    "IDENT_RE",
    "MAX_IDENT",
    "SCHEMA_RE",
    "SLUG_RE",
    "is_identifier",
    "validate_identifier",
    "validate_relation",
    "validate_schema",
    "validate_slug",
]
