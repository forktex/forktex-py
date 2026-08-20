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

"""Snapshot test for ``forktex --help``.

The fixture at ``tests/fixtures/help_output.txt`` captures the exact bytes the
CLI prints for ``forktex --help`` (no TTY, no ANSI colour). It exists for one
reason: the root command taxonomy is the user-visible contract. If a category
moves, a command is added/removed, or a description rewrites, the snapshot
diff makes that explicit in code review instead of buried in user feedback.

Regenerate intentionally by running::

    forktex --help > tests/fixtures/help_output.txt
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "help_output.txt"


def _help_output() -> str:
    """Run ``forktex --help`` exactly as a user would; return the captured stdout.

    Subprocess is the honest path here: spawning Python in-process inherits the
    test runner's environment (pytest fixtures, asyncio loop, etc.) and can
    mask CLI bugs that only show up on a clean invocation.

    The autouse ``isolated_home`` fixture repoints ``HOME`` at a tmp dir, which
    moves Python's *user-site* directory — so a ``pip install --user -e .``
    editable install of ``forktex`` (its ``.pth`` lives under the real
    ``~/.local/...``) becomes invisible to a clean subprocess and the module
    fails to import. Pin ``PYTHONPATH`` to the running interpreter's resolved
    ``sys.path`` so module resolution is HOME-independent — the subprocess sees
    exactly what the test process already imports.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    result = subprocess.run(
        [sys.executable, "-m", "forktex.agent.cli", "--help"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout


def test_root_help_matches_fixture() -> None:
    """``forktex --help`` matches the recorded fixture (taxonomy contract)."""
    actual = _help_output()
    expected = FIXTURE.read_text(encoding="utf-8")
    assert actual == expected, (
        "forktex --help output drifted from the snapshot. If this is intentional "
        "(taxonomy change, new command, description rewrite), refresh the fixture:\n"
        "    forktex --help > tests/fixtures/help_output.txt\n"
        "Then commit the diff alongside the CLI change."
    )


# ── structural assertions (independent of exact text) ────────────────────


@pytest.fixture(scope="module")
def help_text() -> str:
    return _help_output()


def test_categories_are_present(help_text: str) -> None:
    """Every category declared in cli_help renders as a section header.

    Catches the bug where someone adds a new category to ``CATEGORIES`` but
    every entry is filtered out (no registered commands) — the section
    silently disappears. We assert at least one category landed.
    """
    from forktex.agent.cli_help import CATEGORIES

    seen = sum(1 for label, _ in CATEGORIES if f"\n{label}:\n" in help_text)
    assert seen >= 1, "no category section landed in --help"


def test_no_command_silently_dropped(help_text: str) -> None:
    """Every registered top-level command appears somewhere in --help.

    The category renderer falls back to an ``Other`` section for unmapped
    commands; this test asserts the safety net actually runs (a stricter test
    asserts there's no ``Other`` section, see :func:`test_no_orphan_commands`).
    Atoms are explicitly absent — FSD lifecycle verbs moved to ``make`` in
    0.7.0, not the forktex CLI.
    """
    for candidate in (
        "chat",  # core agentic verb
        "run",  # core agentic verb
        "knowledge",  # grounding group
        "arch",  # grounding group (merged graph + manual)
        "cloud",  # services group
        "fsd",  # services group
        "auth",  # services group (replaces top-level `status`)
        "serve",  # services group (generic tool API + MCP)
        "clean",  # housekeeping
    ):
        assert f"  {candidate} " in help_text or f"  {candidate}  " in help_text, (
            f"command {candidate!r} missing from --help"
        )


def test_atoms_no_longer_at_root(help_text: str) -> None:
    """FSD lifecycle atoms (test/build/lint/…) live in `make`, not `forktex`."""
    for atom in ("test", "build", "lint", "format", "typing", "deploy", "publish"):
        assert f"  {atom}  " not in help_text and f"  {atom} " not in help_text, (
            f"FSD atom {atom!r} should not be a top-level forktex command "
            "(use `make` instead)"
        )


def test_no_orphan_commands(help_text: str) -> None:
    """No ``Other`` section in CP A — every command is mapped.

    If this fails, ``CATEGORIES`` in ``forktex.agent.cli_help`` is out of sync
    with the registered commands: add the missing name to the right bucket.
    """
    assert "\nOther:\n" not in help_text, (
        "unexpected 'Other' section — some command isn't in any CATEGORIES bucket"
    )
