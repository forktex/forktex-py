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

"""Cross-service credential management — the ``forktex auth`` group.

Three services (cloud, intelligence, network) share a credential model: each
has its own ``connect`` / ``disconnect`` flow built by
:func:`forktex.agent.auth.cli.build_facet_commands`, and a single status
aggregator (:data:`status_cmd`) reads all three. In 0.7.0 the top-level
``forktex status`` was promoted to ``forktex auth`` (a group whose default
action prints the same status) and the three per-service connect/disconnect
verbs hang underneath as subgroups: ``forktex auth cloud connect``, etc.
That replaces the prior ``forktex network`` top-level group and the
``forktex intelligence connect / disconnect`` paths in one place.
"""

from __future__ import annotations

import asyncclick as click

from forktex.agent.auth.cli import (
    build_facet_commands,
    connect_cloud,
    connect_intelligence,
    connect_network,
    status_cmd,
)
from forktex.agent.auth.status import collect_auth_status
from forktex.agent.auth.types import AuthKind, AuthState, Facet


@click.group(name="auth", invoke_without_command=True)
@click.pass_context
async def auth(ctx: click.Context) -> None:
    """Sign-in state + credentials across services.

    Bare ``forktex auth`` prints the aggregated status across cloud,
    intelligence, and network (the same surface that used to live at
    ``forktex status``). Subgroups (``cloud`` / ``intelligence`` / ``network``)
    expose per-service ``connect`` / ``disconnect``.
    """
    if ctx.invoked_subcommand is None:
        await ctx.invoke(status_cmd)


# Per-service subgroups. ``build_facet_commands`` returns the matched
# ``(connect, disconnect)`` pair for one facet, so reuse the existing factory
# rather than redeclaring eight options here.
for _facet, _connect_impl in (
    ("cloud", connect_cloud),
    ("intelligence", connect_intelligence),
    ("network", connect_network),
):
    _connect, _disconnect = build_facet_commands(_facet, _connect_impl)

    @auth.group(name=_facet)
    async def _facet_group() -> None:
        """Per-service credential commands."""

    _facet_group.add_command(_connect, name="connect")
    _facet_group.add_command(_disconnect, name="disconnect")
del _facet, _connect_impl, _connect, _disconnect, _facet_group


__all__ = [
    "auth",
    "build_facet_commands",
    "status_cmd",
    "connect_cloud",
    "connect_intelligence",
    "connect_network",
    "collect_auth_status",
    "AuthState",
    "Facet",
    "AuthKind",
]
