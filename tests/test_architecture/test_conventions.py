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
import inspect
import pathlib
import textwrap

import pytest

from forktex.error import AppError
from tests.test_architecture.test_public_surface import PACKAGES

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "forktex"

_IS_THE_VOCABULARY = {"error"}


def _classes_defined_in(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


@pytest.mark.parametrize("package", sorted(set(PACKAGES) - _IS_THE_VOCABULARY))
def test_error_classes_live_in_errors_py(package: str) -> None:
    stray: list[str] = []
    for path in sorted((SRC / package).rglob("*.py")):
        if path.name == "errors.py":
            continue
        stray += [f"{path.relative_to(SRC)}:{name}" for name in _classes_defined_in(path) if name.endswith("Error")]
    assert stray == [], f"error classes defined outside {package}/errors.py: {stray}"


@pytest.mark.parametrize("package", PACKAGES)
def test_every_exported_error_derives_from_app_error(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    rogue = [
        name
        for name in module.__all__
        if isinstance(obj := getattr(module, name), type)
        and issubclass(obj, BaseException)
        and not issubclass(obj, AppError)
    ]
    assert rogue == [], f"forktex.{package} exports errors that are not AppError subclasses: {rogue}"


_REGISTRY_FACADES = sorted(
    package
    for package in PACKAGES
    if "from forktex.registry import ClientRegistry" in (SRC / package / "__init__.py").read_text()
)
_REGISTRY_SURFACE = ("register", "get_client", "deregister")


@pytest.mark.parametrize("package", _REGISTRY_FACADES)
def test_registry_facades_expose_the_same_surface(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    missing = [name for name in _REGISTRY_SURFACE if name not in module.__all__]
    assert missing == [], f"forktex.{package} omits registry functions from __all__: {missing}"


@pytest.mark.parametrize("package", _REGISTRY_FACADES)
def test_registry_facades_raise_the_same_error_for_an_unregistered_name(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    error = getattr(module, "ClientNotRegisteredError", None)
    assert error is not None, f"forktex.{package} does not export ClientNotRegisteredError"
    assert issubclass(error, AppError), f"forktex.{package}.ClientNotRegisteredError is not an AppError"


_STDLIB_RAISE_EXEMPT = {"iso"}


@pytest.mark.parametrize("package", sorted(set(PACKAGES) - _STDLIB_RAISE_EXEMPT))
def test_public_functions_do_not_raise_bare_runtime_errors(package: str) -> None:
    offenders: list[str] = []
    for path in sorted((SRC / package).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            call = node.exc
            name = call.func if isinstance(call, ast.Call) else call
            if isinstance(name, ast.Name) and name.id == "RuntimeError":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert offenders == [], f"forktex.{package} raises a bare RuntimeError: {offenders}"


def test_the_stdlib_raise_exemption_is_still_real() -> None:
    importlib.import_module("forktex.iso")

    source = (SRC / "iso" / "__init__.py").read_text(encoding="utf-8")
    assert "raise TypeError" in source or "raise ValueError" in source, (
        "iso no longer raises stdlib errors — drop it from _STDLIB_RAISE_EXEMPT"
    )


REPO = SRC.parents[1]

_WRONG_VERSIONS = {"uuid1", "uuid3", "uuid4", "uuid5"}


def _uuid_calls(path: pathlib.Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if name in _WRONG_VERSIONS:
            found.append((node.lineno, name))
    return found


@pytest.mark.parametrize("tree", ["src", "tests"])
def test_only_uuid7_is_ever_minted(tree: str) -> None:
    offenders = [
        f"{path.relative_to(REPO)}:{lineno} calls {name}()"
        for path in sorted((REPO / tree).rglob("*.py"))
        for lineno, name in _uuid_calls(path)
    ]
    assert offenders == [], f"{tree}/ must mint uuid7 only: {offenders}"


@pytest.mark.parametrize("tree", ["src", "tests"])
def test_no_uuid_is_truncated(tree: str) -> None:
    offenders: list[str] = []
    for path in sorted((REPO / tree).rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "uuid" not in source:
            continue
        for node in ast.walk(ast.parse(source, filename=str(path))):
            if not isinstance(node, ast.Subscript) or not isinstance(node.slice, ast.Slice):
                continue
            if "uuid" in ast.unparse(node.value):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno} slices `{ast.unparse(node)}`")
    assert offenders == [], f"a truncated uuid7 keeps the clock and drops the entropy: {offenders}"


def _exported_errors(module: object) -> list[type[BaseException]]:
    return [
        obj
        for name in module.__all__
        if isinstance(obj := getattr(module, name), type) and issubclass(obj, BaseException)
    ]


def _base_error_name(package: str) -> str:
    return f"{package.capitalize()}Error"


PACKAGES_WITH_A_BASE_ERROR = [
    package for package in PACKAGES if hasattr(importlib.import_module(f"forktex.{package}"), _base_error_name(package))
]


@pytest.mark.parametrize("package", PACKAGES_WITH_A_BASE_ERROR)
def test_a_packages_base_error_catches_every_error_it_exports(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    base: type[BaseException] = getattr(module, _base_error_name(package))
    rogue = sorted(e.__name__ for e in _exported_errors(module) if not issubclass(e, base))
    assert rogue == [], f"forktex.{package} exports {rogue}, which `except {base.__name__}` misses"


TESTS = pathlib.Path(__file__).resolve().parents[1]

SHARED_SETUP = [
    ("async_sessionmaker(", "sessions_for"),
    ('CREATE SCHEMA IF NOT EXISTS "{fresh_schema}"', "the fresh_schema fixture"),
]


@pytest.mark.parametrize(("construct", "replacement"), SHARED_SETUP)
def test_database_setup_goes_through_conftest(construct: str, replacement: str) -> None:
    offenders = [
        f"{path.relative_to(TESTS.parent)}:{lineno}"
        for path in sorted(TESTS.rglob("*.py"))
        if path.name != "conftest.py" and path != pathlib.Path(__file__)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if construct in line
    ]
    assert offenders == [], (
        f"{construct} belongs to {replacement} in tests/conftest.py, not to individual "
        f"modules — eight hand-rolled copies had already drifted apart: {offenders}"
    )


# A base the public models inherit, and the type its subclass hook narrows with:
# both are evaluated while `BaseDBModel` itself is being created, so they cannot
# follow it.
_BASE_CLASS_EXEMPT = {
    ("database", "models.py", "_EagerDefaults"),
    ("database", "models.py", "_MapperArgsDirective"),
    ("database", "models.py", "_inherited_mapper_args"),
}


@pytest.mark.parametrize("package", PACKAGES)
def test_a_module_puts_its_public_surface_above_its_helpers(package: str) -> None:
    out_of_order: list[str] = []
    for path in sorted((SRC / package).glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        seen_private = None
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            if (package, path.name, node.name) in _BASE_CLASS_EXEMPT:
                continue
            if node.name.startswith("_"):
                seen_private = node.name
            elif seen_private is not None:
                out_of_order.append(f"{path.name}:{node.lineno} {node.name} after {seen_private}")
    assert out_of_order == [], (
        f"forktex.{package} defines a public name after a private helper: {out_of_order}. "
        f"A reader meets the surface first and the machinery after it"
    )


@pytest.mark.parametrize("package", PACKAGES)
def test_every_module_ends_with_its_all(package: str) -> None:
    misplaced: list[str] = []
    for path in sorted((SRC / package).glob("*.py")):
        body = ast.parse(path.read_text(encoding="utf-8")).body
        names = [
            target.id
            for node in body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        ]
        if "__all__" not in names:
            misplaced.append(f"{path.name} declares no __all__")
            continue
        last = body[-1]
        if not (isinstance(last, ast.Assign) and any(getattr(t, "id", None) == "__all__" for t in last.targets)):
            misplaced.append(f"{path.name} declares __all__ at line {body[names.index('__all__')].lineno}, not last")
    assert misplaced == [], f"forktex.{package}: {misplaced}"


# Deregisters a per-call client and has nothing to await; it stays `async` so a
# lifespan teardown reads the same for every facade.
_AWAITS_NOTHING = {
    ("storage", "close"),
}


@pytest.mark.parametrize("package", PACKAGES)
def test_an_async_entry_point_awaits_something(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    misleading: list[str] = []
    for name in sorted(getattr(module, "__all__", ())):
        target = getattr(module, name, None)
        if not inspect.iscoroutinefunction(target) or (package, name) in _AWAITS_NOTHING:
            continue
        try:
            tree = ast.parse(textwrap.dedent(inspect.getsource(target)))
        except OSError, SyntaxError:
            continue
        if not any(isinstance(node, ast.Await | ast.AsyncWith | ast.AsyncFor) for node in ast.walk(tree)):
            misleading.append(name)
    assert misleading == [], (
        f"forktex.{package}: {misleading} are `async def` but await nothing, so a caller that "
        f"awaits them in a lifespan believes work was done and a failure would have surfaced. "
        f"Make them sync, or make them do the check their name implies"
    )
