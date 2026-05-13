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

The friendly public name is ``Cloud``; ``ForktexCloudClient`` is its
long-form alias (kept for back-compat with existing import sites).

Usage::

    from forktex.cloud import Cloud, CloudContext

    with Cloud("https://cloud.forktex.com", account_key="ftx-...") as cloud:
        servers = cloud.list_servers()

For standalone usage outside forktex-py: ``pip install forktex-cloud``.
"""

from forktex_cloud import (
    ForktexCloudClient,
    CloudAPIError,
    CloudContext,
    Manifest,
    ManifestError,
    ApiKeyCreated,
    ApiKeyRead,
    EnvironmentRead,
    AuditEventRead,
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

# ``Cloud`` is the friendly public name. Sibling sdk-py 0.2.5+ ships
# the alias at the package root; for older floors (current PyPI 0.2.4
# and below), forktex-py provides the same alias here so
# ``from forktex.cloud import Cloud`` works regardless of which SDK
# floor is installed. Drop this fallback once the dep floor is bumped
# past 0.2.5.
try:
    from forktex_cloud import Cloud  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover — pre-0.2.5 SDK
    Cloud = ForktexCloudClient


__all__ = [
    # High-level API — `Cloud` is canonical; `ForktexCloudClient` is the alias.
    "Cloud",
    "ForktexCloudClient",
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
