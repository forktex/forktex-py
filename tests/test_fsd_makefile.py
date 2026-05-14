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

from forktex.core.paths import require_project_root
from forktex.fsd.loader import load_standard
from forktex.fsd.makefile import (
    generate_makefiles,
    generate_package_makefile,
    generate_root_makefile,
)
from forktex.fsd.profiles import resolve_applicable_atoms
from forktex.manifest.models import ForktexManifest


PROJECT_ROOT = require_project_root(__file__)


def test_workspace_profile_limits_applicable_atoms():
    """forktex-py uses `package/python-library` since v1.2.0 — ops atoms
    are disabled (forktex-py is a CLI library, not a workspace runtime).
    `acceptance` and `manual` are optional in this profile and forktex-py
    declares both."""
    manifest = ForktexManifest.load(PROJECT_ROOT / "forktex.json")
    applicable, disabled = resolve_applicable_atoms(manifest)

    assert applicable is not None
    assert "install" in applicable
    assert "build" in applicable
    assert "sync" in applicable
    assert "acceptance" in applicable
    assert "manual" in applicable
    assert "apply" in disabled
    assert "destroy" in disabled
    assert "monitor" in disabled
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
    assert "python3 -m forktex.agent.help make --project-dir ." in content
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


# ── Variant-syntax custom atoms ─────────────────────────────────────────


def test_custom_atom_with_at_qualifier_canonicalises():
    """A user-declared override key like `apply@web@local` must render as
    the canonical Make target `apply-web-local` (regardless of input order)."""
    manifest = ForktexManifest.model_validate(
        {
            "manifestVersion": "1.1.0",
            "name": "demo",
            "fsd": {
                "version": "1.1.0",
                "profiles": ["workspace/python-monorepo"],
                "atoms": {
                    "apply@local@web": {
                        "commands": ["echo 'apply web at local'"],
                    },
                    "build@api": {
                        "commands": ["docker build -t api ."],
                    },
                    "test@is-interesting": {
                        "commands": ["pytest -m interesting"],
                    },
                },
            },
            "packages": [
                {
                    "name": "demo-api",
                    "path": "api",
                    "version": "0.1.0",
                    "publishable": False,
                    "language": "python",
                },
                {
                    "name": "demo-web",
                    "path": "web",
                    "version": "0.1.0",
                    "publishable": False,
                    "language": "python",
                },
            ],
            "cloud": {"environments": [{"name": "local"}, {"name": "prod"}]},
        }
    )

    content = generate_root_makefile(load_standard(), manifest)

    # `apply@local@web` → canonical `apply-web-local` (service first).
    assert "\napply-web-local:" in content
    assert "apply-local-web:" not in content
    # `build@api` → `build-api`.
    assert "\nbuild-api:" in content
    # Free-form qualifier preserves declared form.
    assert "\ntest-is-interesting:" in content


def test_format_check_renders_for_sub_package_only_workspace():
    """Workspace with only sub-packages (no root-level Python) should still
    get the format-check secondary target via subpackage recursion."""
    manifest = ForktexManifest.model_validate(
        {
            "manifestVersion": "1.1.0",
            "name": "demo",
            "fsd": {
                "version": "1.1.0",
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
    # Workspace recursion form, not the root-level ruff invocation.
    assert "format-check:" in content
    assert "$(MAKE) -C $$pkg format-check" in content
    assert "ruff format --check src/ tests/" not in content
