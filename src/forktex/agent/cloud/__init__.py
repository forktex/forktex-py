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

"""forktex.agent.cloud — Cloud CLI command group.

Registers as a subcommand of the main ``forktex`` CLI.
"""
# ruff: noqa: E402

from __future__ import annotations

import asyncclick as click

from forktex.agent.cloud.init import init
from forktex.agent.cloud.validate import validate
from forktex.agent.cloud.up import up
from forktex.agent.cloud.deploy import deploy
from forktex.agent.cloud.down import down
from forktex.agent.cloud.server import server
from forktex.agent.cloud.project import project
from forktex.agent.cloud.vault import vault
from forktex.agent.cloud.status import status
from forktex.agent.cloud.logs import logs
from forktex.agent.cloud.events import events
from forktex.agent.cloud.dns import dns
from forktex.agent.cloud.ssl import ssl
from forktex.agent.cloud.usage import usage


@click.group()
@click.option(
    "--project-dir", default=None, help="Project root directory (default: cwd)"
)
@click.pass_context
async def cloud(ctx, project_dir):
    """ForkTex Cloud — deploy, manage, and monitor your infrastructure."""
    from pathlib import Path
    from forktex.agent.cloud.settings import load_cloud_context

    project_root = Path(project_dir).resolve() if project_dir else Path.cwd()
    cloud_ctx = load_cloud_context(project_root)
    ctx.ensure_object(dict)
    ctx.obj["project_root"] = project_root
    ctx.obj["cloud_ctx"] = cloud_ctx


# Credential verbs (connect / disconnect) — shared shape with intelligence & network.
from forktex.agent.auth import build_facet_commands, connect_cloud as _connect_cloud

_cloud_connect, _cloud_disconnect = build_facet_commands("cloud", _connect_cloud)
cloud.add_command(_cloud_connect)
cloud.add_command(_cloud_disconnect)

# Register all subcommands
cloud.add_command(init)
cloud.add_command(validate)
cloud.add_command(up)
cloud.add_command(deploy)
cloud.add_command(down)
cloud.add_command(server)
cloud.add_command(project)
cloud.add_command(vault)
cloud.add_command(status)
cloud.add_command(logs)
cloud.add_command(events)
cloud.add_command(dns)
cloud.add_command(ssl)
cloud.add_command(usage)
