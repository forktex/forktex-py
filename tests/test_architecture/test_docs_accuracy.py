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

"""Docs cannot claim an API the library does not have.

When the L0+L1 packages moved here and `forktex_core` became `forktex`, the docs
came with them — still carrying 84 `forktex_core.*` references and pointing at
`grid`/`flow`/`api`, which do not ship in this distribution. Every code example
on every page was wrong, and nothing caught it.

This checks the *import* claims specifically, because they are the mechanically
verifiable part of a doc page: a name that does not resolve is the first thing a
new consumer types. Prose accuracy still needs a human.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC_PATHS = [
    *(p for p in (ROOT / "README.md", ROOT / "AGENTS.md") if p.exists()),
    *sorted((ROOT / "docs").glob("*.md")),
]

_PAREN_IMPORT = re.compile(r"^from (forktex[\w.]*) import \(([^)]*)\)", re.M)
_FLAT_IMPORT = re.compile(r"^from (forktex[\w.]*) import ([\w, ]+)$", re.M)
_PLAIN_IMPORT = re.compile(r"^import (forktex[\w.]*)$", re.M)


def _claims(text: str) -> list[tuple[str, str]]:
    """Every ``(module, name)`` pair a doc says is importable."""
    out: list[tuple[str, str]] = []
    for pattern in (_PAREN_IMPORT, _FLAT_IMPORT):
        for match in pattern.finditer(text):
            module = match.group(1)
            for raw in re.split(r"[,\n]", match.group(2)):
                name = raw.strip().split("#")[0].strip()
                if name.isidentifier():
                    out.append((module, name))
    return out


@pytest.mark.parametrize("doc", DOC_PATHS, ids=lambda p: p.name)
def test_documented_imports_resolve(doc: Path):
    text = doc.read_text(encoding="utf-8")
    unresolved: list[str] = []

    for match in _PLAIN_IMPORT.finditer(text):
        try:
            importlib.import_module(match.group(1))
        except Exception as exc:  # noqa: BLE001 — any import failure is a doc bug
            unresolved.append(f"{match.group(1)} ({type(exc).__name__})")

    for module, name in _claims(text):
        try:
            obj = importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001
            unresolved.append(f"{module} ({type(exc).__name__})")
            continue
        if hasattr(obj, name):
            continue
        # `from pkg import submodule` is legal even though the attribute only
        # appears once the submodule is imported — resolve it that way before
        # calling it stale.
        try:
            importlib.import_module(f"{module}.{name}")
        except ModuleNotFoundError:
            unresolved.append(f"{module}.{name}")

    assert unresolved == [], f"{doc.name} documents names that do not exist: {unresolved}"


@pytest.mark.parametrize("doc", DOC_PATHS, ids=lambda p: p.name)
def test_no_doc_references_the_old_distribution(doc: Path):
    """`forktex_core` / `forktex-core` are dead: the distribution was deleted from
    PyPI and cannot be reinstalled, so an example naming it sends a reader to a 404.

    Only *actionable* references are caught — an import, an install command, or a
    dotted module path. Prose that names the old distribution in order to warn about
    it ("migrating from the old `forktex-core` line", "not a stale `forktex_core`
    reference") is the opposite of a 404 and is allowed.

    The Postgres schema literals (`forktex_flow`, `forktex_grid`) and the logging
    contextvar keys (`forktex_log.*`) are deliberately *not* matched here — they are
    unchanged on purpose, because they name deployed database objects.
    """
    text = doc.read_text(encoding="utf-8")
    actionable = re.findall(
        r"(?:"
        r"(?:from|import)\s+forktex_core\b"  # an import statement
        r"|pip install [^\n`]*forktex-core"  # an install command
        r"|forktex_core\.\w+"  # a dotted module path
        r"|forktex-core\["  # an extras spec
        r")",
        text,
    )
    assert actionable == [], f"{doc.name} tells the reader to use the removed distribution: {actionable}"
