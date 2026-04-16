"""Shared path discovery and resolution helpers.

This module owns:
- global ``.forktex`` config resolution
- project ``.forktex`` config resolution
- centralized project-root and manifest discovery
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


FORKTEX_DIRNAME = ".forktex"
FORKTEX_MANIFEST = "forktex.json"
FORKTEX_LOCAL_MANIFEST = "forktex.local.json"
FORKTEX_DEV_MANIFEST = "forktex.dev.json"


def get_global_config_dir() -> Path:
    """Return the global ForkTex config directory, creating it if needed.

    - Linux/macOS: ``~/.forktex/``
    - Windows: ``%APPDATA%/forktex/``
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "forktex"
        # Fallback for Windows without APPDATA
        return Path.home() / ".forktex"
    return Path.home() / ".forktex"


def resolve_path(path: Optional[str | Path] = None) -> Path:
    """Resolve a filesystem path, defaulting to the current working directory."""

    return Path(path).resolve() if path is not None else Path.cwd().resolve()


def get_manifest_path(project_root: Optional[str | Path] = None) -> Path:
    """Return the canonical root manifest path for a project root."""

    return resolve_path(project_root) / FORKTEX_MANIFEST


def has_manifest(path: str | Path) -> bool:
    """Return True if the given directory contains a root forktex manifest."""

    return get_manifest_path(path).is_file()


def find_project_root(
    start: Optional[str | Path] = None,
    *,
    manifest_name: str = FORKTEX_MANIFEST,
    max_depth: int = 12,
) -> Path | None:
    """Walk upward from ``start`` to find the nearest project root.

    A project root is any directory containing ``manifest_name``.
    """

    current = resolve_path(start)
    if current.is_file():
        current = current.parent

    for _ in range(max_depth + 1):
        if (current / manifest_name).is_file():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def require_project_root(
    start: Optional[str | Path] = None,
    *,
    manifest_name: str = FORKTEX_MANIFEST,
    max_depth: int = 12,
) -> Path:
    """Like ``find_project_root`` but raises if no project root is found."""

    root = find_project_root(start, manifest_name=manifest_name, max_depth=max_depth)
    if root is None:
        raise FileNotFoundError(f"No {manifest_name} found from {resolve_path(start)} upward")
    return root


def find_projects(base_dir: str | Path, names: tuple[str, ...] | list[str] | None = None) -> list[Path]:
    """Find child project directories containing a canonical root manifest."""

    base = resolve_path(base_dir)
    if names:
        return [base / n for n in names if has_manifest(base / n)]
    return sorted(d for d in base.iterdir() if d.is_dir() and has_manifest(d))


def get_project_config_dir(project_root: Optional[str | Path] = None) -> Path:
    """Return the project-level ``.forktex/`` directory.

    Args:
        project_root: Project root path. Defaults to cwd.
    """
    root = Path(project_root) if project_root else Path.cwd()
    return root / FORKTEX_DIRNAME


def get_project_data_path(*parts: str, project_root: Optional[str | Path] = None) -> Path:
    """Return a path under the project ``.forktex`` directory."""

    return get_project_config_dir(project_root).joinpath(*parts)


def get_fsd_dir(project_root: Optional[str | Path] = None) -> Path:
    """Return the project FSD data directory."""

    return get_project_data_path("fsd", project_root=project_root)


def get_fsd_evidence_dir(project_root: Optional[str | Path] = None) -> Path:
    """Return the project FSD evidence directory."""

    return get_project_data_path("fsd", "evidence", project_root=project_root)


def get_architecture_dir(project_root: Optional[str | Path] = None) -> Path:
    """Return the project architecture output directory."""

    return get_project_data_path("architecture", project_root=project_root)


def ensure_global_config_dir() -> Path:
    """Ensure the global config directory exists and return its path."""
    config_dir = get_global_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def ensure_project_config_dir(project_root: Optional[str | Path] = None) -> Path:
    """Ensure the project config directory exists and return its path."""
    config_dir = get_project_config_dir(project_root)
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_global_config_file(filename: str) -> Path:
    """Return the path to a file in the global config directory."""
    return get_global_config_dir() / filename


def get_project_config_file(
    filename: str, project_root: Optional[str | Path] = None
) -> Path:
    """Return the path to a file in the project config directory."""
    return get_project_config_dir(project_root) / filename
