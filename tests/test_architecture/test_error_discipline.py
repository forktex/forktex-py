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
import builtins
import importlib
import inspect
import pathlib

from forktex.error import AppError

from tests.test_architecture.test_public_surface import PACKAGES

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "forktex"

_BUILTIN_EXCEPTIONS = frozenset(
    name for name, obj in vars(builtins).items() if isinstance(obj, type) and issubclass(obj, BaseException)
)

_LAYER_FORCED = frozenset({"iso"})

_VALIDATOR_DECORATORS = frozenset({"field_validator", "model_validator"})

_PROTOCOL_RAISES = {"__getattr__": "AttributeError"}

_PACKAGES_WITH_ERRORS = ["cache", "database", "storage"]
_PACKAGES_WITH_A_DEFAULT = ["cache", "database", "storage"]

_STRUCTURAL = {
    ("database/connection.py", "TypeError"),
    ("database/models.py", "TypeError"),
    ("log/_decorators.py", "TypeError"),
}


def _is_validator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = getattr(target, "id", None) or getattr(target, "attr", None)
        if name in _VALIDATOR_DECORATORS:
            return True
    return False


def test_no_module_raises_a_bare_builtin_at_runtime() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if relative.split("/")[0] in _LAYER_FORCED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        exempt_lines: set[int] = set()
        protocol_lines: dict[int, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            span = range(node.lineno, (node.end_lineno or node.lineno) + 1)
            if _is_validator(node):
                exempt_lines.update(span)
            elif node.name in _PROTOCOL_RAISES:
                protocol_lines.update(dict.fromkeys(span, _PROTOCOL_RAISES[node.name]))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            name = getattr(raised, "id", None)
            if name not in _BUILTIN_EXCEPTIONS:
                continue
            if node.lineno in exempt_lines or (relative, name) in _STRUCTURAL:
                continue
            if protocol_lines.get(node.lineno) == name:
                continue
            offenders.append(f"{relative}:{node.lineno} raises a bare {name}")
    assert offenders == [], (
        "every runtime failure is a named forktex.error leaf, so a transport can map it "
        f"instead of rendering a masked 500: {offenders}"
    )


def test_every_error_leaf_is_reachable_from_its_package() -> None:
    """A leaf in `<package>.errors.__all__` that the facade does not re-export
    forces a consumer to import from the submodule to catch it."""
    offenders: list[str] = []
    checked: list[str] = []
    for package in PACKAGES:
        try:
            errors = importlib.import_module(f"forktex.{package}.errors")
        except ModuleNotFoundError:
            continue
        checked.append(package)
        facade = importlib.import_module(f"forktex.{package}")
        unreachable = sorted(set(getattr(errors, "__all__", ())) - set(getattr(facade, "__all__", ())))
        offenders += [f"forktex.{package} does not export {name}" for name in unreachable]
    assert checked == _PACKAGES_WITH_ERRORS, (
        f"this gate skips a package with no errors.py, so it must declare which ones it covers: "
        f"checked {checked}, declared {_PACKAGES_WITH_ERRORS}"
    )
    assert offenders == [], f"{offenders}"


def test_default_and_require_default_mean_the_same_thing_on_every_facade() -> None:
    """0.13.0 unified the *name* `default()` but not its contract: some facades
    raised where others returned None, so a caller could not write one idiom."""
    offenders: list[str] = []
    checked: list[str] = []
    for package in PACKAGES:
        facade = importlib.import_module(f"forktex.{package}")
        has_default = "default" in getattr(facade, "__all__", ())
        has_require = "require_default" in getattr(facade, "__all__", ())
        if has_default and not has_require:
            offenders.append(f"forktex.{package} exports default() without require_default()")
        if has_require and not has_default:
            offenders.append(f"forktex.{package} exports require_default() without default()")
        if not has_default:
            continue
        checked.append(package)
        returns = inspect.signature(facade.default).return_annotation
        if "None" not in str(returns):
            offenders.append(f"forktex.{package}.default() -> {returns}, which cannot report absence")
        if facade.default() is not None:
            offenders.append(f"forktex.{package}.default() returned a handle with nothing registered")
        try:
            facade.require_default()
        except Exception as exc:
            if not isinstance(exc, AppError):
                offenders.append(f"forktex.{package}.require_default() raised {type(exc).__name__}, not an AppError")
        else:
            offenders.append(f"forktex.{package}.require_default() returned with nothing registered")
    assert checked == _PACKAGES_WITH_A_DEFAULT, (
        f"this gate skips a package without default(), so it must declare which ones it covers: "
        f"checked {checked}, declared {_PACKAGES_WITH_A_DEFAULT}"
    )
    assert offenders == [], f"{offenders}"
