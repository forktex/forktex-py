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


from forktex.database import ddl, filters, reflect
from forktex.database.connection import (
    Database,
    close_engine,
    get_session,
    init_engine,
    savepoint,
    session_scope,
    unmanaged_session,
    with_transactional_session,
)
from forktex.database.crud import (
    PageResponse,
    ScrollResponse,
    create,
    find_one_by,
    get,
    list_all,
    paginate,
    paginate_scroll,
)
from forktex.database.errors import DatabaseNotInitializedError, TransactionBoundaryError
from forktex.database.identifiers import (
    is_identifier,
    validate_identifier,
    validate_relation,
    validate_schema,
    validate_slug,
)
from forktex.database.integrity import integrity_boundary, read_boundary
from forktex.database.locks import (
    advisory_key,
    advisory_lock,
    key_from_uuid,
    try_advisory_lock,
    xact_lock,
)
from forktex.database.migrate import SchemaMigrationRunner
from forktex.database.models import (
    AuditMixin,
    BaseDBModel,
    JsonModelColumn,
    NamespacedMixin,
    ReprMixin,
    TimestampMixin,
    UtcDateTime,
    substrate_base,
)
from forktex.database.pagination import (
    Page,
    decode_cursor,
    encode_cursor,
    keyset_predicate,
)

__all__ = [
    "AuditMixin",
    "BaseDBModel",
    "Database",
    "DatabaseNotInitializedError",
    "JsonModelColumn",
    "NamespacedMixin",
    "Page",
    "PageResponse",
    "ReprMixin",
    "SchemaMigrationRunner",
    "ScrollResponse",
    "TimestampMixin",
    "TransactionBoundaryError",
    "UtcDateTime",
    "advisory_key",
    "advisory_lock",
    "close_engine",
    "create",
    "ddl",
    "decode_cursor",
    "encode_cursor",
    "filters",
    "find_one_by",
    "get",
    "get_session",
    "init_engine",
    "integrity_boundary",
    "is_identifier",
    "key_from_uuid",
    "keyset_predicate",
    "list_all",
    "paginate",
    "paginate_scroll",
    "read_boundary",
    "reflect",
    "savepoint",
    "session_scope",
    "substrate_base",
    "try_advisory_lock",
    "unmanaged_session",
    "validate_identifier",
    "validate_relation",
    "validate_schema",
    "validate_slug",
    "with_transactional_session",
    "xact_lock",
]
