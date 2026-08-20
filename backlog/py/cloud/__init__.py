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

"""forktex.cloud — Re-exports from the standalone ``forktex_cloud`` SDK.

Usage::

    from forktex.cloud import Cloud, CloudContext

    with Cloud("https://cloud.forktex.com", account_key="ftx-...") as cloud:
        servers = cloud.list_servers()

For standalone usage outside forktex-py: ``pip install forktex-cloud``.
"""

from forktex_cloud import (
    Cloud,
    CloudAPIError,
    CloudContext,
    Manifest,
    ManifestError,
    ApiKeyCreated,
    ApiKeyRead,
    EnvironmentRead,
    HealthRead,
    JobResponse,
    MeResponse,
    OrgRead,
    ProjectRead,
    ServerRead,
    StatusResponse,
    TokenResponse,
    UserRead,
    VaultGetResponse,
    WorkspaceRead,
)

# Added to the SDK in 0.3.0 — guard so forktex-py still works against
# the 0.2.4 PyPI floor while local-dev uses the in-tree 0.3.0 sdk-py.
try:
    from forktex_cloud import AuditEventRead  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover — older SDK floor
    AuditEventRead = None  # type: ignore[assignment]


__all__ = [
    # High-level API
    "Cloud",
    "CloudAPIError",
    "CloudContext",
    "Manifest",
    "ManifestError",
    # Wire-level models (advanced — prefer high-level API)
    "ApiKeyCreated",
    "ApiKeyRead",
    "EnvironmentRead",
    "AuditEventRead",
    "HealthRead",
    "JobResponse",
    "MeResponse",
    "OrgRead",
    "ProjectRead",
    "ServerRead",
    "StatusResponse",
    "TokenResponse",
    "UserRead",
    "VaultGetResponse",
    "WorkspaceRead",
]
