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

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "forktex"

PACKAGES = [
    "api",
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
    "worker",
]

_EXTRA_BACKED = {
    "api": ("fastapi", "starlette"),
    "vault": ("cryptography",),
    "storage": ("aioboto3", "botocore"),
    "queue": ("arq",),
    "vector": ("qdrant_client",),
    "worker": ("arq",),
    "store": ("pymongo",),
}


@pytest.mark.parametrize("package", PACKAGES)
def test_every_package_declares_all(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    assert hasattr(module, "__all__"), f"forktex.{package} has no __all__"
    assert module.__all__, f"forktex.{package}.__all__ is empty"


@pytest.mark.parametrize("package", PACKAGES)
def test_no_package_exports_a_private_name(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    private = sorted(n for n in module.__all__ if n.startswith("_"))
    assert private == [], f"forktex.{package} exports private-looking names: {private}"


@pytest.mark.parametrize("package", PACKAGES)
def test_every_exported_name_resolves(package: str) -> None:
    module = importlib.import_module(f"forktex.{package}")
    missing = sorted(n for n in module.__all__ if not hasattr(module, n))
    assert missing == [], f"forktex.{package}.__all__ names unimportable attributes: {missing}"


def test_optional_dependencies_are_imported_lazily_or_name_their_extra() -> None:
    blocker = (
        "import builtins\n"
        "_blocked_names = {deps!r}\n"
        "_real = builtins.__import__\n"
        "def _blocked(name, *a, **k):\n"
        "    root = name.split('.')[0]\n"
        "    if root in _blocked_names:\n"
        "        raise ModuleNotFoundError(f'No module named {{root!r}}')\n"
        "    return _real(name, *a, **k)\n"
        "builtins.__import__ = _blocked\n"
        "try:\n"
        "    import forktex.{pkg}\n"
        "except ImportError as exc:\n"
        "    print('IMPORTERROR:' + str(exc))\n"
        "else:\n"
        "    print('LAZY')\n"
    )
    failures: list[str] = []
    for package, deps in sorted(_EXTRA_BACKED.items()):
        result = subprocess.run(
            [sys.executable, "-c", blocker.format(deps=set(deps), pkg=package)],
            capture_output=True,
            text=True,
            check=False,
        )
        out = result.stdout.strip()
        if out == "LAZY":
            continue
        if out.startswith("IMPORTERROR:"):
            message = out.removeprefix("IMPORTERROR:")
            if f"forktex[{package}]" not in message:
                failures.append(
                    f"forktex.{package}: import fails without {deps} and the error does not "
                    f"name the extra — got {message!r}"
                )
            continue
        failures.append(f"forktex.{package}: unexpected probe output {out!r}\n{result.stderr}")
    assert failures == [], "\n".join(failures)


@pytest.mark.parametrize("package", PACKAGES)
def test_every_package_has_a_consumer_doc(package: str) -> None:
    doc = SRC.parents[1] / "docs" / f"{package}.md"
    assert doc.exists(), f"missing docs/{package}.md for forktex.{package}"


def test_database_exports_everything_the_standards_tell_consumers_to_use() -> None:
    import forktex.database as db

    documented = {
        "Database",
        "get_session",
        "session_scope",
        "init_engine",
        "close_engine",
        "savepoint",
        "unmanaged_session",
        "TransactionBoundaryError",
        "BaseDBModel",
        "substrate_base",
        "UtcDateTime",
        "AuditMixin",
        "TimestampMixin",
        "NamespacedMixin",
        "JsonModelColumn",
        "Page",
        "encode_cursor",
        "decode_cursor",
        "keyset_predicate",
        "advisory_lock",
        "try_advisory_lock",
        "xact_lock",
        "advisory_key",
        "key_from_uuid",
        "validate_identifier",
        "validate_schema",
        "validate_slug",
        "validate_relation",
        "is_identifier",
        "integrity_boundary",
        "read_boundary",
        "SchemaMigrationRunner",
        "ddl",
        "reflect",
    }
    missing = sorted(documented - set(db.__all__))
    assert missing == [], f"documented in standards/code-reuse.md but not exported: {missing}"
