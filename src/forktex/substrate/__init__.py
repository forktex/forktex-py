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

"""``forktex.substrate`` — the single filesystem authority for ``.forktex/``.

forktex-py is the only component that knows ``.forktex/`` exists; the libraries
(forktex_core, forktex_cloud, …) deal in pure data. This package unifies the
on-disk surface:

* :mod:`forktex.substrate.paths` — the path factories (bucketed layout).
* :mod:`forktex.substrate.spec`  — the EntrySpec contract + audit.

The atomic, audited write seam (``tracked_write`` / ``install_audit_hook``) and
the touch registry currently live in :mod:`forktex.graph.io_proxy` /
:mod:`forktex.graph.registry`; import them from there. See
``standard.forktex-architecture``.
"""

from __future__ import annotations

from forktex.substrate import paths
from forktex.substrate.spec import (
    GLOBAL_SPEC,
    PROJECT_SPEC,
    AuditEntry,
    EntryKind,
    EntrySpec,
    MatchResult,
    NestedAuditReport,
    Sensitivity,
    audit,
    audit_tree,
    discover_nested_forktex_dirs,
    required_entries,
    secret_entries,
    spec_for,
    validate_path,
)

__all__ = [
    "paths",
    "EntryKind",
    "Sensitivity",
    "EntrySpec",
    "PROJECT_SPEC",
    "GLOBAL_SPEC",
    "MatchResult",
    "AuditEntry",
    "NestedAuditReport",
    "spec_for",
    "validate_path",
    "required_entries",
    "secret_entries",
    "audit",
    "audit_tree",
    "discover_nested_forktex_dirs",
]
