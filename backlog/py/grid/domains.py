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

"""Namespace taxonomy — forktex-py's logical state-space → grid namespaces.

core-py treats a grid ``namespace`` as an opaque scope string; isolation is the
consumer's to define. forktex-py partitions its state into non-overlapping
namespaces so each domain is its own grid state space:

- ``system``               — global state, the project registry, prefs.
- ``project:{fingerprint}`` — per-project state (config, agent runs, arch).
- ``knowledge``            — engineering/library catalog, RAG references.
- ``sandbox:{id}``         — POC sandboxes / flows / runs.

``{fingerprint}`` is the stable project identity (see ``forktex.grid.fingerprint``)
so a project's namespace is reproducible without storing absolute paths.
"""

from __future__ import annotations

SYSTEM = "system"
KNOWLEDGE = "knowledge"


def project_ns(fingerprint: str) -> str:
    """Namespace for a project's state, keyed by its stable fingerprint."""
    return f"project:{fingerprint}"


def sandbox_ns(sandbox_id: str) -> str:
    """Namespace for a POC sandbox / flow / run."""
    return f"sandbox:{sandbox_id}"


def is_project_ns(namespace: str) -> bool:
    return namespace.startswith("project:")


def is_sandbox_ns(namespace: str) -> bool:
    return namespace.startswith("sandbox:")


__all__ = [
    "SYSTEM",
    "KNOWLEDGE",
    "project_ns",
    "sandbox_ns",
    "is_project_ns",
    "is_sandbox_ns",
]
