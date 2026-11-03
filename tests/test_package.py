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
"""What a consumer relies on when importing `forktex`."""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

MODULES = ["api", "cache", "database", "error", "iso", "log", "storage", "types"]


def _fresh(probe: str) -> str:
    """Run in a new interpreter, so nothing earlier tests imported or registered leaks in."""
    return subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.parametrize("name", MODULES)
def test_every_exported_name_is_importable(name: str) -> None:
    module = importlib.import_module(f"forktex.{name}")
    assert module.__all__
    assert [n for n in module.__all__ if not hasattr(module, n)] == []


@pytest.mark.parametrize("name", MODULES)
def test_the_package_root_exposes_every_module(name: str) -> None:
    import forktex

    assert getattr(forktex, name) is importlib.import_module(f"forktex.{name}")


def test_the_package_root_refuses_a_name_it_does_not_have() -> None:
    import forktex

    with pytest.raises(AttributeError, match="no attribute 'nope'"):
        forktex.nope  # noqa: B018
    with pytest.raises(AttributeError):
        forktex.subprocess  # noqa: B018
    assert dir(forktex) == sorted(forktex.__all__)


def test_importing_one_module_does_not_import_the_others() -> None:
    probe = (
        "import sys\n"
        "from forktex.iso import to_iso\n"
        "print([m for m in ('fastapi', 'sqlalchemy', 'redis', 'aioboto3') if m in sys.modules])\n"
    )
    assert _fresh(probe) == "[]"


@pytest.mark.parametrize("name", ["cache", "database", "storage"])
def test_with_nothing_configured_default_is_none_and_require_default_raises(name: str) -> None:
    probe = (
        f"from forktex import {name} as facade\n"
        "from forktex.error import AppError\n"
        "print(facade.default() is None)\n"
        "try:\n"
        "    facade.require_default()\n"
        "except AppError:\n"
        "    print('refused')\n"
    )
    assert _fresh(probe).splitlines() == ["True", "refused"]
