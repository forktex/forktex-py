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

"""``AsyncLazyGroup`` — an ``asyncclick.Group`` whose subcommands import lazily.

Subcommands registered via :meth:`AsyncLazyGroup.add_lazy_command` don't trigger
an import of their module at registration time. The first invocation (or first
``--help`` for that specific subcommand) imports the leaf and caches the resolved
command on the group, so subsequent lookups skip the import machinery entirely.

The point: ``forktex --help`` needs to *list* commands, not load them. Lazy means
the user pays for what they invoke, not for everything the CLI could do. This is
the canonical Click recipe, adapted to asyncclick and to forktex's optional-dep
pattern: missing optional deps surface as a friendly ``ClickException`` on
invocation, not a registration-time crash.

Usage::

    @click.group(invoke_without_command=True, cls=AsyncLazyGroup)
    async def cli(ctx): ...

    cli.add_lazy_command("network", "forktex.agent.network:network")
    cli.add_lazy_command(
        "knowledge",
        "forktex.agent.knowledge.cli:knowledge",
        optional=True,
        install_hint="pip install 'forktex-core[fractal]'",
    )

Eager ``cli.add_command`` keeps working alongside lazy entries — the two
registries are merged in :meth:`list_commands` and :meth:`get_command`.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

import asyncclick as click


@dataclass(frozen=True)
class _LazyEntry:
    """One pending lazy registration.

    ``spec`` is ``"package.module:click_object"`` — the dotted path to the module
    plus the name of the ``click.Command`` / ``click.Group`` instance inside it.
    ``optional`` flips on the friendly "command unavailable" message for missing
    third-party extras. ``short_help`` is the one-line description shown in
    ``--help`` output; cached so listing the parent group doesn't have to import
    the leaf just to read its docstring.
    """

    spec: str
    optional: bool = False
    install_hint: str | None = None
    short_help: str | None = None


class AsyncLazyGroup(click.Group):
    """A Click / asyncclick group with on-demand subcommand imports."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lazy_commands: dict[str, _LazyEntry] = {}

    def add_lazy_command(
        self,
        name: str,
        spec: str,
        *,
        short_help: str | None = None,
        optional: bool = False,
        install_hint: str | None = None,
    ) -> None:
        """Register ``name`` to resolve from ``spec`` on first access.

        ``spec`` is ``"package.module:attribute"``. ``short_help`` is the one-line
        description rendered in the parent's ``--help`` output — supply it so
        listing the parent group doesn't have to import the leaf just to read its
        docstring (the very thing lazy loading is meant to avoid). If ``optional``
        is true, a missing module raises a ``ClickException`` (with
        ``install_hint`` if provided) on invocation rather than failing
        registration — letting the rest of the CLI work even when an extra isn't
        installed.
        """
        self._lazy_commands[name] = _LazyEntry(
            spec=spec,
            optional=optional,
            install_hint=install_hint,
            short_help=short_help,
        )

    # ── Click overrides ────────────────────────────────────────────────────

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return all command names without importing any lazy modules."""
        return sorted(set(self.commands) | set(self._lazy_commands))

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Resolve a command; import + cache on first access of a lazy entry."""
        if cmd_name in self.commands:
            return self.commands[cmd_name]
        entry = self._lazy_commands.get(cmd_name)
        if entry is None:
            return None
        module_path, _, attr = entry.spec.rpartition(":")
        if not module_path:  # invalid spec — surface as a registration bug
            raise click.UsageError(
                f"lazy command {cmd_name!r}: malformed spec {entry.spec!r} "
                f"(expected 'package.module:attribute')"
            )
        try:
            cmd = getattr(importlib.import_module(module_path), attr)
        except ModuleNotFoundError as exc:
            if not entry.optional:
                raise
            hint = (
                f"\n  Install it with: {entry.install_hint}"
                if entry.install_hint
                else ""
            )
            missing = getattr(exc, "name", None) or str(exc)
            raise click.ClickException(
                f"Command '{cmd_name}' is unavailable (missing dependency: {missing}).{hint}"
            ) from exc
        # Cache so the next lookup skips this function entirely.
        self.commands[cmd_name] = cmd
        return cmd

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Render the "Commands" section without loading lazy entries.

        Two specialisations over Click's default:

        1. **Lazy-aware.** Click's default calls ``get_command`` on every
           subcommand to read its ``short_help``; for a lazy group, that defeats
           the whole point (``--help`` would import every leaf). We use the cached
           ``short_help`` for lazy-but-unloaded entries and only fall through to
           the normal path for already-resolved (or never-lazy) entries.
        2. **Category-grouped.** Top-level groups carry a ``CATEGORIES`` map
           (see :mod:`forktex.agent.cli_help`) declaring an ordered set of
           ``(label, names)`` buckets. Rows render in that order under named
           sections, ``make help``-style: cyan name padded to a fixed column
           width, then short description. Names not in any category drop into
           a final ``Other`` section so the help never silently swallows
           commands. When no category map is reachable (any subgroup invocation,
           every ``Group`` that isn't the root CLI) we fall back to a single
           flat ``Commands`` section — preserving the prior behaviour.
        """
        rows: dict[str, str] = {}
        for subcommand in self.list_commands(ctx):
            entry = self._lazy_commands.get(subcommand)
            if (
                entry is not None
                and subcommand not in self.commands
                and entry.short_help is not None
            ):
                rows[subcommand] = entry.short_help
                continue
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or getattr(cmd, "hidden", False):
                continue
            rows[subcommand] = cmd.get_short_help_str(formatter.width)

        if not rows:
            return

        # Only the root CLI carries a category map. Subgroup help still uses the
        # single-section path that ships in Click; lazy short_help caching above
        # already keeps subgroup --help cheap.
        categories = _root_categories_for(ctx)
        if categories is None:
            with formatter.section("Commands"):
                formatter.write_dl(list(rows.items()))
            return

        from forktex.agent.cli_help import (
            ANSI_CYAN,
            ANSI_RESET,
            name_column_width,
        )

        use_colour = bool(getattr(ctx, "color", None))
        width = name_column_width(list(rows.keys()))
        rendered: set[str] = set()

        def _emit_row(name: str, short_help: str) -> None:
            # ``formatter.write()`` doesn't honour ``current_indent`` (only
            # ``write_text`` / ``write_dl`` do). Prefix manually so rows align
            # under the section heading just like Click's default sections do.
            indent = " " * formatter.current_indent
            label = (
                f"{ANSI_CYAN}{name:<{width}}{ANSI_RESET}"
                if use_colour
                else f"{name:<{width}}"
            )
            formatter.write(f"{indent}{label}  {short_help}\n")

        for label, names in categories:
            present = [(n, rows[n]) for n in names if n in rows]
            if not present:
                continue
            with formatter.section(label):
                for name, short_help in present:
                    _emit_row(name, short_help)
                    rendered.add(name)

        leftover = [(n, rows[n]) for n in sorted(rows) if n not in rendered]
        if leftover:
            with formatter.section("Other"):
                for name, short_help in leftover:
                    _emit_row(name, short_help)


def _root_categories_for(ctx: click.Context) -> list[tuple[str, list[str]]] | None:
    """Return the root CLI's category map if ``ctx`` is rendering its help.

    Subgroup help (e.g. ``forktex cloud --help``) reuses :class:`AsyncLazyGroup`
    for its lazy-aware ``format_commands`` but should keep the single ``Commands``
    section Click ships. We detect "root CLI" by ``ctx.parent is None``; that
    keeps the category routing scoped to the top level.
    """
    if ctx.parent is not None:
        return None
    try:
        from forktex.agent.cli_help import CATEGORIES
    except ImportError:  # pragma: no cover — defensive
        return None
    return CATEGORIES


__all__ = ["AsyncLazyGroup"]
