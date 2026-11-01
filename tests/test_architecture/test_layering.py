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


from __future__ import annotations

import ast
import importlib
import pathlib
from enum import StrEnum

import pytest

from forktex.types import BaseValueObject

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "forktex"


class Level(StrEnum):
    PRIMITIVE = "primitive"
    MECHANIC = "mechanic"
    FACADE = "facade"


class ModuleLayer(BaseValueObject):
    name: str
    level: Level
    may_import: frozenset[str] = frozenset()


LIBRARY: tuple[ModuleLayer, ...] = (
    ModuleLayer(name="iso", level=Level.PRIMITIVE),
    ModuleLayer(name="types", level=Level.PRIMITIVE, may_import=frozenset({"iso"})),
    ModuleLayer(name="error", level=Level.PRIMITIVE, may_import=frozenset({"types"})),
    ModuleLayer(name="log", level=Level.PRIMITIVE, may_import=frozenset({"iso"})),
    ModuleLayer(name="registry", level=Level.MECHANIC),
    ModuleLayer(name="api", level=Level.FACADE),
    ModuleLayer(name="cache", level=Level.FACADE),
    ModuleLayer(name="database", level=Level.FACADE),
    ModuleLayer(name="graph", level=Level.FACADE),
    ModuleLayer(name="queue", level=Level.FACADE),
    ModuleLayer(name="storage", level=Level.FACADE),
    ModuleLayer(name="store", level=Level.FACADE),
    ModuleLayer(name="vault", level=Level.FACADE),
    ModuleLayer(name="vector", level=Level.FACADE),
)


def _names(level: Level) -> frozenset[str]:
    return frozenset(module.name for module in LIBRARY if module.level is level)


def _importable_by(module: ModuleLayer) -> frozenset[str]:
    match module.level:
        case Level.PRIMITIVE:
            return module.may_import
        case Level.MECHANIC:
            return _names(Level.PRIMITIVE)
        case Level.FACADE:
            return _names(Level.PRIMITIVE) | _names(Level.MECHANIC)


def _modules() -> list[pathlib.Path]:
    return sorted(SRC.rglob("*.py"))


def _level_name(path: pathlib.Path) -> str:
    relative = path.relative_to(SRC)
    return relative.parts[0] if len(relative.parts) > 1 else relative.stem


def _forktex_imports(path: pathlib.Path) -> set[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            targets = [node.module] if node.module else []
            if node.module == "forktex":
                targets += [f"forktex.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        else:
            continue
        for target in targets:
            parts = (target or "").split(".")
            if len(parts) >= 2 and parts[0] == "forktex":
                found.add((node.lineno, parts[1]))
    return found


def _globals_rebound_in(package: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in _modules():
        if _level_name(path) != package:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = sorted({name for node in ast.walk(tree) if isinstance(node, ast.Global) for name in node.names})
        if names:
            found[str(path.relative_to(SRC.parent.parent))] = names
    return found


@pytest.mark.parametrize("module", LIBRARY, ids=lambda m: m.name)
def test_a_module_imports_only_what_its_level_allows(module: ModuleLayer) -> None:
    allowed = _importable_by(module)
    offenders = [
        f"{path.relative_to(SRC.parent.parent)}:{lineno} imports forktex.{imported}"
        for path in _modules()
        if _level_name(path) == module.name
        for lineno, imported in sorted(_forktex_imports(path))
        if imported != module.name and imported not in allowed
    ]
    assert offenders == [], (
        f"forktex.{module.name} is a {module.level}, so it may import only {sorted(allowed)}: {offenders}"
    )


def test_every_level_bearing_name_is_assigned_a_level() -> None:
    declared = {module.name for module in LIBRARY}
    present = {_level_name(path) for path in _modules()} - {"__init__"}
    assert present == declared, (
        f"every top-level module must be declared in LIBRARY. "
        f"Unplaced: {sorted(present - declared)}; declared but absent: {sorted(declared - present)}"
    )


@pytest.mark.parametrize("facade", sorted(_names(Level.FACADE)), ids=lambda name: name)
def test_process_wide_state_is_reachable_without_the_global(facade: str) -> None:
    rebound = _globals_rebound_in(facade)
    if not rebound:
        return
    handle = facade.capitalize()
    module = importlib.import_module(f"forktex.{facade}")
    assert hasattr(module, handle), (
        f"forktex.{facade} rebinds process-wide state ({rebound}) but exports no {handle}, so "
        f"that state is unreachable except through the module-level default"
    )
