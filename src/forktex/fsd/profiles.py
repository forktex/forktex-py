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


PROFILE_CATALOG: dict[str, RuntimeProfile] = {
    "workspace/python-monorepo": RuntimeProfile(
        id="workspace/python-monorepo",
        required=(
            "deps",
            "format",
            "lint",
            "test",
            "security-audit",
            "start",
            "stop",
            "logs",
            "build",
            "publish",
            "ci",
            "clean",
            "help",
        ),
        optional=("typecheck", "license", "codegen", "codegen-check"),
        disabled=(
            "db-migrate",
            "db-reset",
            "seed",
            "compliance",
        ),
    ),
    "package/python-library": RuntimeProfile(
        id="package/python-library",
        required=("deps", "format", "lint", "test", "build", "publish", "ci", "clean", "help"),
        optional=("security-audit", "typecheck", "license"),
        disabled=(
            "start",
            "stop",
            "logs",
            "db-migrate",
            "db-reset",
            "seed",
            "codegen",
            "deploy",
            "backup",
            "rollback",
            "monitoring",
            "compliance",
        ),
    ),
    "package/python-sdk": RuntimeProfile(
        id="package/python-sdk",
        required=("deps", "format", "lint", "test", "build", "publish", "ci", "clean", "help"),
        optional=("security-audit", "typecheck", "license", "codegen-check"),
        disabled=(
            "start",
            "stop",
            "logs",
            "db-migrate",
            "db-reset",
            "seed",
            "codegen",
            "deploy",
            "backup",
            "rollback",
            "monitoring",
            "compliance",
        ),
    ),
}


def resolve_profile_ids(
    manifest: ForktexManifest,
    *,
    package_manifest: ForktexManifest | None = None,
) -> list[str]:
    """Resolve applicable runtime profiles for a manifest unit."""

    config: FSDConfig | None = package_manifest.fsd if package_manifest and package_manifest.fsd else manifest.fsd
    if config and config.profiles:
        return config.profiles
    return ["package/python-library"] if package_manifest else []


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
