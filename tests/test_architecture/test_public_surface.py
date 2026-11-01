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
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "forktex"

PACKAGES = [
    "api",
    "cache",
    "database",
    "error",
    "iso",
    "log",
    "storage",
    "types",
]


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


@pytest.mark.parametrize("package", PACKAGES)
def test_the_package_root_exposes_every_module(package: str) -> None:
    import forktex

    assert package in forktex.__all__, f"import forktex does not expose forktex.{package}"
    assert getattr(forktex, package, None) is importlib.import_module(f"forktex.{package}")


@pytest.mark.parametrize("package", PACKAGES)
def test_every_package_has_a_consumer_doc(package: str) -> None:
    doc = SRC.parents[1] / "docs" / f"{package}.md"
    assert doc.exists(), f"missing docs/{package}.md for forktex.{package}"


def test_database_exports_everything_the_standards_tell_consumers_to_use() -> None:
    import forktex.database as db

    documented = {
        "Database",
        "transactional_session",
        "yield_transactional_session",
        "init_engine",
        "close_engine",
        "savepoint",
        "open_session",
        "get_engine",
        "TransactionBoundaryError",
        "BaseDBModel",
        "substrate_base",
        # `UtcTimestamp` upstream: the standard still names it `UtcDateTime`, which
        # collided with `forktex.types.UtcDateTime`, a Pydantic annotation.
        "UtcTimestamp",
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


def test_the_default_database_delegates_mirror_the_database_methods() -> None:
    from forktex.database import connection

    methods = {
        name
        for name, value in vars(connection.Database).items()
        if not name.startswith("_") and callable(value) and name != "dispose"
    }
    delegates = {name for name in connection.__all__ if not name[0].isupper()}
    assert methods <= delegates, f"Database methods with no module-level delegate: {sorted(methods - delegates)}"


def test_connection_exports_no_name_that_is_not_defined_there() -> None:
    from forktex.database import connection

    assert sorted(connection.__all__) == connection.__all__
    undefined = [name for name in connection.__all__ if not hasattr(connection, name)]
    assert undefined == []
