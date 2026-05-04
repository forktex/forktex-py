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

"""``forktex intelligence`` command group.

All intelligence-driven verbs live under this group so the three services
(cloud / intelligence / network) sit at the same level:

- ``intelligence ask <text>`` — single-shot question (scriptable).
- ``intelligence run <task>`` — orchestrated task.
- ``intelligence scrape <url>`` — agentic browser scraper.
- ``intelligence index-ecosystem`` — knowledge ingestion.
- ``intelligence status`` — API reachability + whoami.
- ``intelligence connect`` / ``intelligence disconnect`` — credential management.

For interactive chat, just run bare ``forktex`` — the root loop auto-opens
the chat REPL when intelligence is reachable.
"""

from __future__ import annotations

import asyncclick as click

from forktex.agent.auth import (
    build_facet_commands,
    connect_intelligence as _connect_intelligence,
)
from forktex.agent.commands.index_ecosystem import index_ecosystem
from forktex.agent.intelligence.cli.chat import ask
from forktex.agent.intelligence.cli.run import run
from forktex.agent.scraper.cli import scrape
from forktex.agent.ui.console import console, error, info


@click.group()
async def intelligence():
    """ForkTex Intelligence — ask, run, scrape, index, connect.

    Credentials are captured via ``forktex intelligence connect``.
    For interactive chat, run bare ``forktex``.
    """
    pass


@intelligence.command(name="status")
@click.option("--project", "-d", default=None, help="Project directory")
async def status_cmd(project):
    """Show Intelligence API health + whoami."""
    from pathlib import Path

    from forktex.agent.intelligence.settings import get_intelligence_settings
    from forktex_intelligence.client.client import ForktexIntelligenceClient

    root = str(Path(project).resolve() if project else Path.cwd())
    settings = get_intelligence_settings(project_root=root)

    console.print(f"[bold]Endpoint:[/bold] {settings.endpoint or '[dim]not set[/dim]'}")
    console.print(
        f"[bold]API Key:[/bold] {'***' + settings.api_key[-4:] if settings.api_key else '[dim]not set[/dim]'}"
    )

    if not getattr(settings, "is_configured", False) and not (
        settings.endpoint and settings.api_key
    ):
        info("Not configured. Run: forktex intelligence connect")
        return

    client = ForktexIntelligenceClient(settings.endpoint, settings.api_key)
    try:
        health = await client.health()
        whoami = await client.whoami()
        console.print(
            f"[bold green]Status:[/bold green] OK (v{getattr(health, 'version', '?')})"
        )
        if isinstance(whoami, dict):
            if whoami.get("org_id"):
                console.print(f"[bold]Org:[/bold] {whoami['org_id']}")
            if whoami.get("model"):
                console.print(f"[bold]Model:[/bold] {whoami['model']}")
    except Exception as exc:
        error(f"intelligence status failed: {exc}")
    finally:
        await client.close()


# Credential verbs (connect / disconnect) — shared shape with cloud & network.
_intel_connect, _intel_disconnect = build_facet_commands(
    "intelligence", _connect_intelligence
)

intelligence.add_command(ask)
intelligence.add_command(run)
intelligence.add_command(scrape)
intelligence.add_command(index_ecosystem)
intelligence.add_command(_intel_connect)
intelligence.add_command(_intel_disconnect)


def register_intelligence_commands(cli: click.Group) -> None:
    """Register the single ``intelligence`` group on the main CLI.

    Interactive chat is the bare ``forktex`` entry point; scriptable verbs
    (``ask``, ``run``, ``scrape``, ``index-ecosystem``) live under this group.
    """
    cli.add_command(intelligence)


__all__ = ["register_intelligence_commands", "intelligence"]
