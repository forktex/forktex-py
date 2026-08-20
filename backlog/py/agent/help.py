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

"""CLI entrypoint for generated help output."""

from __future__ import annotations

import argparse
from pathlib import Path

from forktex.fsd.help_tree import build_help_tree, render_help_rich, render_help_text
from forktex.fsd.loader import load_standard
from forktex.manifest.models import ForktexManifest


_CLI_COLLISIONS = {"clean"}


def _known_atom_cli_ids(standard) -> set[str]:
    return {atom.id for atom in standard.atoms} - _CLI_COLLISIONS


def render_project_help(
    *,
    project_dir: Path,
    atom_id: str | None = None,
    rich: bool = True,
) -> str | None:
    standard = load_standard()
    manifest = ForktexManifest.load(project_dir / "forktex.json")
    tree = build_help_tree(
        standard,
        manifest,
        cli_atoms=_known_atom_cli_ids(standard),
    )
    if rich and render_help_rich(tree, atom_id=atom_id):
        return None
    return render_help_text(tree, atom_id=atom_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m forktex.agent.help")
    sub = parser.add_subparsers(dest="command", required=True)

    make = sub.add_parser("make", help="Render generated Makefile help")
    make.add_argument("--project-dir", default=".", help="Project root")
    make.add_argument("--atom", default=None, help="Limit help to one atom")
    make.add_argument(
        "--plain",
        action="store_true",
        help="Disable Rich and emit deterministic plain text",
    )

    args = parser.parse_args(argv)
    if args.command == "make":
        rendered = render_project_help(
            project_dir=Path(args.project_dir).resolve(),
            atom_id=args.atom,
            rich=not args.plain,
        )
        if rendered is not None:
            print(rendered)
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
