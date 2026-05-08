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

from pathlib import Path

from forktex.fsd.loader import load_standard
from forktex.fsd.makefile import (
    generate_makefiles,
    generate_package_makefile,
    generate_root_makefile,
)
from forktex.fsd.profiles import resolve_applicable_atoms
from forktex.manifest.models import ForktexManifest


PROJECT_ROOT = Path("/home/samanu/Desktop/forktex/forktex-py")


def test_workspace_profile_limits_applicable_atoms():
    manifest = ForktexManifest.load(PROJECT_ROOT / "forktex.json")
    applicable, disabled = resolve_applicable_atoms(manifest)

    assert applicable is not None
    assert "install" in applicable
    assert "build" in applicable
    assert "sync" in applicable
    assert "apply" in applicable
    assert "rollback" in disabled


def test_generate_root_makefile_contains_expected_targets():
    manifest = ForktexManifest.load(PROJECT_ROOT / "forktex.json")
    standard = load_standard()
    generated = generate_makefiles(
        project_root=PROJECT_ROOT,
        standard=standard,
        manifest=manifest,
    )

    content = generated[0].content
    assert ".DEFAULT_GOAL := help" in content
    assert "PROJECT_NAME := forktex-py" in content
    assert (
        "install-global: ## Install the latest local forktex CLI globally in editable mode"
        in content
    )
    assert "format-check: ## Check formatting without rewriting files" in content
    assert "deps-lock: ## Lock dependencies" in content


def test_generate_root_makefile_skips_root_python_secondaries_for_workspace_only_root():
    manifest = ForktexManifest.model_validate(
        {
            "manifestVersion": "1.0.0",
            "name": "demo-workspace",
            "fsd": {
                "version": "1.0.0",
                "profiles": ["workspace/python-monorepo"],
            },
            "packages": [
                {
                    "name": "demo-sdk",
                    "path": "sdk-py",
                    "version": "0.1.0",
                    "publishable": True,
                    "language": "python",
                }
            ],
        }
    )

    content = generate_root_makefile(load_standard(), manifest)

    assert "ruff format --check src/ tests/" not in content
    assert "deps-lock: ## Lock dependencies" not in content
    assert (
        "install-global: ## Install the latest local forktex CLI globally"
        not in content
    )
    assert "local: apply" in content


def test_package_override_reenables_disabled_atom_and_suppresses_secondary_duplicates():
    root_manifest = ForktexManifest.model_validate(
        {
            "manifestVersion": "1.0.0",
            "name": "demo-workspace",
            "fsd": {
                "version": "1.0.0",
                "profiles": ["workspace/python-monorepo"],
            },
        }
    )
    package_manifest = ForktexManifest.model_validate(
        {
            "manifestVersion": "1.0.0",
            "name": "demo-api",
            "fsd": {
                "version": "1.0.0",
                "profiles": ["package/python-sdk"],
                "atoms": {
                    "codegen": {
                        "commands": ["python codegen.py"],
                    },
                    "format-check": {
                        "commands": ["python verify_format.py"],
                    },
                    "lint-fix": {
                        "commands": ["python fix_lint.py"],
                    },
                },
            },
            "packages": [
                {
                    "name": "demo-api",
                    "path": ".",
                    "version": "1.0.0",
                    "publishable": False,
                    "language": "python",
                }
            ],
        }
    )

    content = generate_package_makefile(
        load_standard(),
        root_manifest,
        package_manifest,
    )

    assert ".DEFAULT_GOAL := help" in content
    assert "codegen:" in content
    assert "python codegen.py" in content
    assert content.count("format-check:") == 1
    assert "python verify_format.py" in content
    assert content.count("lint-fix:") == 1
    assert "python fix_lint.py" in content
