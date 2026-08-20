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

# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""forktex cloud provider — manage compute and DNS provider credentials."""

from __future__ import annotations

import asyncclick as click
from forktex.agent.cloud.errors import translate_cloud_errors


@click.group()
def provider():
    """Manage compute and DNS provider credentials."""


@provider.command("list")
@click.pass_context
@translate_cloud_errors
async def provider_list(ctx):
    """List all registered provider credentials."""
    _gate(ctx, "list_providers")


@provider.command("add")
@click.argument("kind", type=click.Choice(["compute", "dns"]))
@click.option("--token", required=True, help="API token or credential string")
@click.option("--label", default="", help="Optional label to identify this credential")
@click.option("--env", default=None, help="Scope to a specific environment name")
@click.pass_context
@translate_cloud_errors
async def provider_add(ctx, kind, token, label, env):
    """Register a provider credential.

    KIND is 'compute' (for VPS provisioning) or 'dns' (for DNS management).
    """
    _gate(ctx, "add_provider")


@provider.command("verify")
@click.argument("credential_id")
@click.pass_context
@translate_cloud_errors
async def provider_verify(ctx, credential_id):
    """Test connectivity for a provider credential."""
    _gate(ctx, "verify_provider")


@provider.command("remove")
@click.argument("credential_id")
@click.pass_context
@translate_cloud_errors
async def provider_remove(ctx, credential_id):
    """Remove a provider credential."""
    _gate(ctx, "delete_provider")


def _gate(ctx, missing_method: str) -> None:
    click.echo(
        f"  `forktex cloud provider` is not surfaced by SDK 0.3.0 "
        f"(client.{missing_method} missing). Manage providers via the "
        f"cloud-API admin endpoints directly until the SDK grows the method.",
        err=True,
    )
    raise click.exceptions.Exit(2)
