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

"""Built-in FSD applicability profiles.

Profiles refine the atom catalog for common software shapes without changing
the atom semantics themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from forktex.manifest.models import FSDConfig, ForktexManifest


@dataclass(frozen=True)
class RuntimeProfile:
    id: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    disabled: tuple[str, ...] = ()

    @property
    def applicable_atoms(self) -> set[str]:
        return set(self.required) | set(self.optional)


# Profiles speak the v1.3.0 atom catalog (see standard.json):
# install / format / lint / typing / test / security / license / sync / docs /
# manual / build / publish / clean / apply / destroy / monitor /
# rollback / acceptance / backup / seed.
PROFILE_CATALOG: dict[str, RuntimeProfile] = {
    "workspace/python-monorepo": RuntimeProfile(
        id="workspace/python-monorepo",
        required=(
            "install",
            "format",
            "lint",
            "test",
            "security",
            "apply",
            "destroy",
            "monitor",
            "build",
            "publish",
            "clean",
        ),
        optional=(
            "typing",
            "license",
            "sync",
            "docs",
            "manual",
            "acceptance",
        ),
        disabled=(
            "rollback",
            "backup",
            "seed",
        ),
    ),
    "package/python-library": RuntimeProfile(
        id="package/python-library",
        required=(
            "install",
            "format",
            "lint",
            "test",
            "build",
            "publish",
            "clean",
        ),
        optional=(
            "security",
            "typing",
            "license",
            "sync",
            "docs",
            "manual",
            "acceptance",
        ),
        disabled=(
            "apply",
            "destroy",
            "monitor",
            "rollback",
            "backup",
            "seed",
        ),
    ),
    "package/python-sdk": RuntimeProfile(
        id="package/python-sdk",
        required=(
            "install",
            "format",
            "lint",
            "test",
            "build",
            "publish",
            "clean",
        ),
        optional=(
            "security",
            "typing",
            "license",
            "sync",
            "docs",
            "manual",
            "acceptance",
        ),
        disabled=(
            "apply",
            "destroy",
            "monitor",
            "rollback",
            "backup",
            "seed",
        ),
    ),
    "docs/knowledge-directory": RuntimeProfile(
        id="docs/knowledge-directory",
        required=(
            "format",
            "lint",
            "test",
            "clean",
            "docs",
        ),
        optional=("build", "manual"),
        disabled=(
            "install",
            "typing",
            "security",
            "license",
            "sync",
            "apply",
            "destroy",
            "monitor",
            "publish",
            "rollback",
            "backup",
            "acceptance",
            "seed",
        ),
    ),
}


def resolve_profile_ids(
    manifest: ForktexManifest,
    *,
    package_manifest: ForktexManifest | None = None,
) -> list[str]:
    """Resolve applicable runtime profiles for a manifest unit."""

    config: FSDConfig | None = (
        package_manifest.fsd
        if package_manifest and package_manifest.fsd
        else manifest.fsd
    )
    if config and config.profiles:
        return config.profiles
    if package_manifest:
        return ["package/python-library"]
    # Root manifest with no declared profile: infer from `kind`.
    if manifest.kind == "KnowledgeDirectory":
        return ["docs/knowledge-directory"]
    return []


def resolve_applicable_atoms(
    manifest: ForktexManifest,
    *,
    package_manifest: ForktexManifest | None = None,
) -> tuple[set[str] | None, set[str]]:
    """Return applicable and disabled atom ids for the current unit.

    ``None`` applicable means "all atoms are applicable".
    """

    profile_ids = resolve_profile_ids(manifest, package_manifest=package_manifest)
    if not profile_ids:
        return None, set()

    applicable: set[str] = set()
    disabled: set[str] = set()
    for profile_id in profile_ids:
        profile = PROFILE_CATALOG.get(profile_id)
        if not profile:
            continue
        applicable |= profile.applicable_atoms
        disabled |= set(profile.disabled)

    return applicable, disabled
