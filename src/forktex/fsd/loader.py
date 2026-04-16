"""Load the FSD standard and project configuration."""

from __future__ import annotations

from pathlib import Path

from forktex.core.paths import get_manifest_path
from forktex.data.fsd import STANDARD_PATH
from forktex.fsd.models import FSDStandard
from forktex.manifest.models import FSDConfig, ForktexManifest, MANIFEST_VERSION


def _major(version: str | None) -> str | None:
    if not version:
        return None
    return version.split(".", 1)[0]


def ensure_manifest_supported(manifest: ForktexManifest) -> None:
    """Validate the loaded forktex.json schema version."""
    expected_major = _major(MANIFEST_VERSION)
    actual_major = _major(manifest.manifest_version)
    if actual_major and actual_major != expected_major:
        raise ValueError(
            f"Unsupported manifestVersion {manifest.manifest_version!r}; "
            f"expected major {expected_major}.x"
        )


def ensure_fsd_supported(standard: FSDStandard, config: FSDConfig | None) -> None:
    """Validate the project FSD contract against the loaded standard."""
    declared = config.version if config else None
    if not declared:
        return
    declared_major = _major(declared)
    actual_major = _major(standard.version)
    if declared_major != actual_major:
        raise ValueError(
            f"Unsupported FSD version {declared!r}; loaded standard is {standard.version!r}"
        )


def load_standard(custom_path: Path | None = None) -> FSDStandard:
    """Load the FSD standard definition.

    Resolution:
      1. Explicit ``custom_path`` if provided.
      2. Bundled standard.json shipped with the forktex package.
    """
    path = custom_path or STANDARD_PATH
    return FSDStandard.from_json(path)


def load_project_config(project_root: Path) -> FSDConfig | None:
    """Load the ``fsd`` section from a project's forktex.json.

    Returns None if forktex.json doesn't exist or has no ``fsd`` section.
    """
    manifest_path = get_manifest_path(project_root)
    if not manifest_path.is_file():
        return None
    manifest = ForktexManifest.load(manifest_path)
    return manifest.fsd
