"""forktex.agent.intelligence.cli — CLI commands for Intelligence API interaction.

Registers top-level commands: chat, ask, run
And the `intelligence` subgroup for: intelligence init
"""

from __future__ import annotations

import asyncclick as click

from forktex.agent.intelligence.cli.chat import chat, ask
from forktex.agent.intelligence.cli.run import run
from forktex.agent.intelligence.cli.init import intelligence
from forktex.agent.commands.index_ecosystem import index_ecosystem


def register_intelligence_commands(cli: click.Group) -> None:
    """Register intelligence CLI commands on the main CLI group.

    - ``chat``, ``ask``, ``run`` are top-level commands
    - ``intelligence`` is a subgroup with ``init``, ``index-ecosystem``
    """
    cli.add_command(chat)
    cli.add_command(ask)
    cli.add_command(run)
    intelligence.add_command(index_ecosystem)
    cli.add_command(intelligence)
