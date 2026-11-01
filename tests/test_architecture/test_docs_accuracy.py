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
import re
import textwrap
from pathlib import Path

import pytest

from tests.test_architecture.test_public_surface import PACKAGES

HOUSE_SECTIONS = ("Wiring", "Public surface", "Errors", "Gotchas")

ROOT = Path(__file__).resolve().parents[2]
DOC_PATHS = [
    *(p for p in (ROOT / "README.md", ROOT / "AGENTS.md") if p.exists()),
    *sorted((ROOT / "docs").glob("*.md")),
]

CLAIMING_PATHS = [*DOC_PATHS, *(p for p in [ROOT / "CHANGELOG.md"] if p.exists())]

_PAREN_IMPORT = re.compile(r"^from (forktex[\w.]*) import \(([^)]*)\)", re.M)
_FLAT_IMPORT = re.compile(r"^from (forktex[\w.]*) import ([\w, ]+)$", re.M)
_PLAIN_IMPORT = re.compile(r"^import (forktex[\w.]*)$", re.M)


def _claims(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pattern in (_PAREN_IMPORT, _FLAT_IMPORT):
        for match in pattern.finditer(text):
            module = match.group(1)
            for raw in re.split(r"[,\n]", match.group(2)):
                name = raw.strip().split("#")[0].strip()
                if name.isidentifier():
                    out.append((module, name))
    return out


@pytest.mark.parametrize("doc", CLAIMING_PATHS, ids=lambda p: p.name)
def test_documented_imports_resolve(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    unresolved: list[str] = []

    for match in _PLAIN_IMPORT.finditer(text):
        try:
            importlib.import_module(match.group(1))
        except Exception as exc:
            unresolved.append(f"{match.group(1)} ({type(exc).__name__})")

    for module, name in _claims(text):
        try:
            obj = importlib.import_module(module)
        except Exception as exc:
            unresolved.append(f"{module} ({type(exc).__name__})")
            continue
        if hasattr(obj, name):
            continue
        try:
            importlib.import_module(f"{module}.{name}")
        except ModuleNotFoundError:
            unresolved.append(f"{module}.{name}")

    assert unresolved == [], f"{doc.name} documents names that do not exist: {unresolved}"


@pytest.mark.parametrize("doc", DOC_PATHS, ids=lambda p: p.name)
def test_no_doc_references_the_old_distribution(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    actionable = re.findall(
        r"(?:"
        r"(?:from|import)\s+forktex_core\b"
        r"|pip install [^\n`]*forktex-core"
        r"|forktex_core\.\w+"
        r"|forktex-core\["
        r")",
        text,
    )
    assert actionable == [], f"{doc.name} tells the reader to use the removed distribution: {actionable}"


@pytest.mark.parametrize("package", PACKAGES)
def test_every_exported_name_is_documented_on_its_page(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    page = (ROOT / "docs" / f"{package}.md").read_text(encoding="utf-8")
    mentioned = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)", page))
    exported = list(getattr(module, "__all__", ()))
    missing = sorted(name for name in exported if name not in mentioned)
    assert exported, f"forktex.{package} exports nothing, so this gate checked nothing"
    assert missing == [], (
        f"docs/{package}.md documents no name for {missing} — a consumer cannot "
        f"discover an export that appears on no page"
    )


@pytest.mark.parametrize("package", PACKAGES)
def test_every_page_carries_the_house_sections(package: str) -> None:
    page = (ROOT / "docs" / f"{package}.md").read_text(encoding="utf-8")
    headings = set(re.findall(r"^## (.+)$", page, re.M))
    missing = [section for section in HOUSE_SECTIONS if section not in headings]
    assert missing == [], (
        f"docs/{package}.md is missing {missing}. The README promises every page covers "
        f"install, wiring, the public surface, the error contract and the gotchas, so a "
        f"reader finds the same answer in the same place on every page"
    )


_DOCUMENTED_CODE = re.compile(r"`(\w+Error)`[^\n]*?`AppErrorCode\.(\w+)`")


@pytest.mark.parametrize("package", PACKAGES)
def test_a_documented_error_code_is_the_code_the_class_carries(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    page = (ROOT / "docs" / f"{package}.md").read_text(encoding="utf-8")
    wrong = []
    for name, documented in _DOCUMENTED_CODE.findall(page):
        cls = getattr(module, name, None)
        if cls is None or not isinstance(cls, type):
            continue
        actual = getattr(cls, "code", None)
        if actual is not None and actual.name != documented:
            wrong.append(f"{name}: docs say {documented}, class carries {actual.name}")
    assert wrong == [], f"docs/{package}.md states the wrong error code: {wrong}"


_PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.S)


@pytest.mark.parametrize("doc", CLAIMING_PATHS, ids=lambda p: p.name)
def test_every_documented_python_example_parses(doc: Path) -> None:
    broken: list[str] = []
    for index, block in enumerate(_PYTHON_BLOCK.findall(doc.read_text(encoding="utf-8")), 1):
        try:
            ast.parse(textwrap.dedent(block))
        except SyntaxError as exc:
            broken.append(f"block {index} line {exc.lineno}: {exc.msg}")
    assert broken == [], f"{doc.name} shows Python a consumer cannot run: {broken}"
