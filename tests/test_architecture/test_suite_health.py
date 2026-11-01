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
import collections
import pathlib
import re


TESTS = pathlib.Path(__file__).resolve().parents[1]
CONFTEST = TESTS / "conftest.py"


class _RenameOnly(ast.NodeTransformer):
    def visit_Name(self, node: ast.Name) -> ast.Name:
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = "_"
        node.annotation = None
        return node


def _modules() -> list[pathlib.Path]:
    return sorted(TESTS.rglob("*.py"))


def _functions(path: pathlib.Path) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _is_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any("fixture" in ast.unparse(d) for d in node.decorator_list)


def _is_autouse(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any("autouse" in ast.unparse(d) for d in node.decorator_list)


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = node.args
    return [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs if a.arg not in {"self", "cls"}]


def _normalised_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    statements = [ast.fix_missing_locations(_RenameOnly().visit(ast.parse(ast.unparse(s)))) for s in node.body]
    return ast.dump(ast.Module(body=statements, type_ignores=[]))


def test_no_two_test_functions_share_a_body() -> None:
    bodies: dict[str, list[str]] = collections.defaultdict(list)
    for path in _modules():
        for node in _functions(path):
            if len(node.body) < 3:
                continue
            bodies[_normalised_body(node)].append(f"{path.relative_to(TESTS.parent)}:{node.lineno} {node.name}")
    copies = [group for group in bodies.values() if len(group) > 1]
    assert copies == [], (
        "these bodies are identical once local names are normalised, so a change has to be made "
        f"in every copy: {copies}"
    )


def test_every_fixture_is_used() -> None:
    defined: dict[str, str] = {}
    requested: set[str] = set()
    for path in _modules():
        source = path.read_text(encoding="utf-8")
        for node in _functions(path):
            if _is_fixture(node):
                if not _is_autouse(node):
                    defined[node.name] = f"{path.relative_to(TESTS.parent)}:{node.lineno}"
                requested.update(_parameters(node))
            else:
                requested.update(_parameters(node))
        requested.update(re.findall(r'usefixtures\(\s*"([^"]+)"', source))
    dead = sorted(f"{name} ({where})" for name, where in defined.items() if name not in requested)
    assert dead == [], f"a fixture nothing requests is dead weight: {dead}"


def test_no_module_redefines_a_conftest_fixture() -> None:
    shared = {node.name for node in _functions(CONFTEST) if _is_fixture(node)}
    shadowed = [
        f"{path.relative_to(TESTS.parent)}:{node.lineno} {node.name}"
        for path in _modules()
        if path != CONFTEST
        for node in _functions(path)
        if _is_fixture(node) and node.name in shared
    ]
    assert shadowed == [], (
        "a module-level fixture with a conftest name shadows the shared one, which is how two "
        f"identical database-session fixtures came to exist: {shadowed}"
    )


# Substituting a library internal is how a suite stops testing anything. The
# entry below injects a failure a real container cannot be made to produce,
# against a real container.
_FAULT_INJECTION = {
    ("test_cache/test_ops.py", "Cache"),
}


def test_no_test_substitutes_a_library_internal() -> None:
    offenders: list[str] = []
    for path in sorted(TESTS.rglob("test_*.py")):
        relative = path.relative_to(TESTS).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "setattr" or not node.args:
                continue
            if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "monkeypatch"):
                continue
            target = node.args[0]
            root = target
            while isinstance(root, ast.Attribute):
                root = root.value
            name = root.id if isinstance(root, ast.Name) else ast.unparse(target)
            if (relative, name) in _FAULT_INJECTION:
                continue
            offenders.append(f"{relative}:{node.lineno} patches {ast.unparse(target)}")
    assert offenders == [], (
        f"a test replaced a library internal instead of running against a container: {offenders}. "
        f"Use the real thing, or add it to _FAULT_INJECTION with the failure it injects"
    )
