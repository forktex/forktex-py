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


"""Conventions the 12 shipped packages hold in common, checked rather than trusted.

Two rules from `docs/engineering/standards/`, both of which had live violations
until this pass:

- `package-layout.md:130-132` — "`errors.py` is always `errors.py`". Five packages
  defined error classes inline instead, three of them buried in a 155-line
  `__init__.py`.
- `error-envelope.md:56-58` — a library's public errors derive from `AppError`, so
  a consumer's single boundary renders them instead of letting a bare
  `RuntimeError` escape as a masked 500. `cache` raised a bare one.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

from forktex.error import AppError

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "forktex"

#: The shipped packages, same list as `test_public_surface.PACKAGES`.
PACKAGES = [
    "cache",
    "database",
    "error",
    "graph",
    "iso",
    "log",
    "queue",
    "storage",
    "store",
    "types",
    "vault",
    "vector",
]

#: `error` IS the shared error vocabulary — its classes belong in its own
#: `__init__.py`, not in a nested `errors.py`.
_IS_THE_VOCABULARY = {"error"}


def _classes_defined_in(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


@pytest.mark.parametrize("package", sorted(set(PACKAGES) - _IS_THE_VOCABULARY))
def test_error_classes_live_in_errors_py(package: str):
    """An error class defined outside `errors.py` is a convention break.

    Not cosmetic: the whole point of a fixed filename is that a reader (or an
    agent) can find every failure mode of a package without reading it. Three of
    `storage`'s were previously invisible inside its `__init__.py`.
    """
    stray: list[str] = []
    for path in sorted((SRC / package).rglob("*.py")):
        if path.name == "errors.py":
            continue
        stray += [f"{path.relative_to(SRC)}:{name}" for name in _classes_defined_in(path) if name.endswith("Error")]
    assert stray == [], f"error classes defined outside {package}/errors.py: {stray}"


@pytest.mark.parametrize("package", PACKAGES)
def test_every_exported_error_derives_from_app_error(package: str):
    """A public error that is not an `AppError` escapes the consumer's boundary."""
    module = importlib.import_module(f"forktex.{package}")
    rogue = [
        name
        for name in module.__all__
        if isinstance(obj := getattr(module, name), type)
        and issubclass(obj, BaseException)
        and not issubclass(obj, AppError)
    ]
    assert rogue == [], f"forktex.{package} exports errors that are not AppError subclasses: {rogue}"


#: The three facades that expose a named-client registry. `code-reuse.md` rule 2
#: says a mechanic needed in a second package should be promoted; at the third use
#: these had already diverged — only `storage` logged, only `store` omitted
#: `deregister` from its `__all__`. Until a shared `ClientRegistry` exists, this
#: pins the surface so they cannot drift apart again.
_REGISTRY_FACADES = ["storage", "store", "vector"]
_REGISTRY_SURFACE = ("register", "get_client", "deregister")


@pytest.mark.parametrize("package", _REGISTRY_FACADES)
def test_registry_facades_expose_the_same_surface(package: str):
    module = importlib.import_module(f"forktex.{package}")
    missing = [name for name in _REGISTRY_SURFACE if name not in module.__all__]
    assert missing == [], f"forktex.{package} omits registry functions from __all__: {missing}"


@pytest.mark.parametrize("package", _REGISTRY_FACADES)
def test_registry_facades_raise_the_same_error_for_an_unregistered_name(package: str):
    """Each defines its own `ClientNotRegisteredError`; all must be `AppError`s so
    one consumer boundary covers every backend."""
    module = importlib.import_module(f"forktex.{package}")
    error = getattr(module, "ClientNotRegisteredError", None)
    assert error is not None, f"forktex.{package} does not export ClientNotRegisteredError"
    assert issubclass(error, AppError), f"forktex.{package}.ClientNotRegisteredError is not an AppError"


#: `iso` raises stdlib TypeError/ValueError for argument errors, not AppError.
#: Recorded rather than silently tolerated: `forktex.error` imports `forktex.types`
#: which imports `forktex.iso`, so an `iso -> error` edge closes a cycle between
#: three level-0 primitives. See the exemption note in `iso/__init__.py`.
#: Listing it here means a *new* stdlib raise elsewhere is a deliberate act that
#: shows up in review, not a silent drift.
_STDLIB_RAISE_EXEMPT = {"iso"}


@pytest.mark.parametrize("package", sorted(set(PACKAGES) - _STDLIB_RAISE_EXEMPT))
def test_public_functions_do_not_raise_bare_runtime_errors(package: str):
    """`error-envelope.md`: a library's errors bridge onto `AppError`, so one
    consumer boundary renders them instead of letting a bare `RuntimeError`
    escape as a masked 500.

    Only `RuntimeError` is policed here, deliberately. `TypeError`/`ValueError`
    for a wrong-typed argument are what a Python caller already expects and are
    not transport-facing; a bare `RuntimeError` is the one that reads as
    "something broke" and has no catch site.
    """
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


def test_the_stdlib_raise_exemption_is_still_real():
    """A stale exemption is a rule that has quietly stopped applying."""
    import forktex.iso  # noqa: F401

    source = (SRC / "iso" / "__init__.py").read_text(encoding="utf-8")
    assert "raise TypeError" in source or "raise ValueError" in source, (
        "iso no longer raises stdlib errors — drop it from _STDLIB_RAISE_EXEMPT"
    )
    assert "deliberate, recorded exception" in source, "the iso exemption lost its written rationale"
