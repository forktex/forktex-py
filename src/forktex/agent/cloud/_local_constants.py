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

"""Constants and helpers copied from forktex-cloud SDK private surfaces.

Origin: ``forktex_cloud.bridge.local_compose`` (single-underscore
prefix → SDK-private). forktex-py used to import them directly but
that breaks silently any time the SDK refactors. The local copy here
is the contract until those symbols are promoted to the SDK's public
API.

TODO(forktex-cloud): file an issue requesting public exports for
``OBSERVABILITY_PORTS`` and ``allocate_host_ports`` (or an
equivalent), then drop this module and re-import.
"""

from __future__ import annotations

from typing import Any


__all__ = ["OBSERVABILITY_PORTS", "allocate_host_ports"]


# Ports reserved by observability services (Loki).
OBSERVABILITY_PORTS: set[int] = {3100}


def allocate_host_ports(
    services: list[dict[str, Any]],
    *,
    reserved: set[int] | None = None,
) -> dict[str, int]:
    """Allocate host ports for compute services, avoiding conflicts.

    Honours each service's explicit ``hostPort`` first, then auto-
    assigns starting from 8080 (or the service's declared port) for
    every remaining ``compute`` service. Reserved ports are never
    handed out.

    Mirrors ``forktex_cloud.bridge.local_compose._allocate_host_ports``;
    keep them in sync until the SDK promotes the function to public
    API.
    """
    used: set[int] = set(reserved or ())
    mapping: dict[str, int] = {}

    for svc in services:
        host_port = svc.get("hostPort")
        if host_port is not None:
            mapping[svc["id"]] = int(host_port)
            used.add(int(host_port))

    for svc in services:
        sid = svc["id"]
        if sid in mapping:
            continue
        if svc.get("type", "compute") != "compute":
            continue
        port = svc.get("port", 80)
        candidate = 8080 if port == 80 else port
        while candidate in used:
            candidate += 1
        mapping[sid] = candidate
        used.add(candidate)

    return mapping
