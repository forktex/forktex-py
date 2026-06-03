# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""Layering guards — keep the dependency arrows pointing the right way.

Ring 1 (substrate) is the lowest layer; it must not depend on higher layers
(graph, agent). This pins the substrate→graph violation we removed (``Scope``
now lives in ``substrate.spec``; graph imports it from substrate, not vice versa).
"""

from __future__ import annotations

import ast
from pathlib import Path

import forktex.substrate as substrate

_SUBSTRATE_DIR = Path(substrate.__file__).parent
_FORBIDDEN_PREFIXES = ("forktex.graph", "forktex.agent")


def _imported_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_substrate_does_not_import_higher_layers():
    offenders: list[str] = []
    for py_file in sorted(_SUBSTRATE_DIR.rglob("*.py")):
        for mod in _imported_modules(py_file):
            if mod.startswith(_FORBIDDEN_PREFIXES):
                offenders.append(f"{py_file.name} imports {mod}")
    assert not offenders, "substrate must not depend on graph/agent: " + "; ".join(
        offenders
    )
