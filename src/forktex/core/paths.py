"""Shared path discovery and resolution helpers.

Canonical ``.forktex/`` and ``~/.forktex/`` paths live in
``forktex_cloud.paths`` (V1 spec). This module re-exports the most common
helpers and adds forktex-py-specific project-root discovery utilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from forktex_cloud import paths as _cloud_paths


FORKTEX_MANIFEST = "forktex.json"
FORKTEX_LOCAL_MANIFEST = "forktex.local.json"


# ── Project-root discovery (forktex-py specific) ──

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
    """Walk upward from ``start`` to find the nearest project root."""
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
        raise FileNotFoundError(
            f"No {manifest_name} found from {resolve_path(start)} upward"
        )
    return root


def find_projects(
    base_dir: str | Path, names: tuple[str, ...] | list[str] | None = None
) -> list[Path]:
    """Find child project directories containing a canonical root manifest."""
    base = resolve_path(base_dir)
    if names:
        return [base / n for n in names if has_manifest(base / n)]
    return sorted(d for d in base.iterdir() if d.is_dir() and has_manifest(d))


# ── Thin wrappers around forktex_cloud.paths (V1 spec) ──

def get_global_config_dir() -> Path:
    """Return the global ForkTex config directory (``~/.forktex/`` / ``%APPDATA%/forktex/``)."""
    return _cloud_paths.global_dir()


def get_project_config_dir(project_root: Optional[str | Path] = None) -> Path:
    """Return the project-level ``.forktex/`` directory."""
    root = Path(project_root) if project_root else Path.cwd()
    return _cloud_paths.project_dir(root)


def get_project_data_path(
    *parts: str, project_root: Optional[str | Path] = None
) -> Path:
    """Return a path under the project ``.forktex/`` directory."""
    return get_project_config_dir(project_root).joinpath(*parts)


def get_fsd_dir(project_root: Optional[str | Path] = None) -> Path:
    """Return the project FSD data directory."""
    root = Path(project_root) if project_root else Path.cwd()
    return _cloud_paths.project_dir(root) / "fsd"


def get_fsd_evidence_dir(project_root: Optional[str | Path] = None) -> Path:
    """Return the project FSD evidence directory."""
    root = Path(project_root) if project_root else Path.cwd()
    return _cloud_paths.fsd_evidence_dir(root)


def get_architecture_dir(project_root: Optional[str | Path] = None) -> Path:
    """Return the project architecture output directory."""
    root = Path(project_root) if project_root else Path.cwd()
    return _cloud_paths.architecture_dir(root)


def ensure_global_config_dir() -> Path:
    """Ensure the global config directory exists and return its path."""
    _cloud_paths.ensure_global_dir()
    return _cloud_paths.global_dir()


def ensure_project_config_dir(project_root: Optional[str | Path] = None) -> Path:
    """Ensure the project ``.forktex/`` directory exists (with gitignore + schema version)."""
    root = Path(project_root) if project_root else Path.cwd()
    _cloud_paths.ensure_project_dirs(root)
    return _cloud_paths.project_dir(root)


def get_global_config_file(filename: str) -> Path:
    """Return the path to a file in the global config directory."""
    return _cloud_paths.global_dir() / filename


def get_project_config_file(
    filename: str, project_root: Optional[str | Path] = None
) -> Path:
    """Return the path to a file in the project ``.forktex/`` directory."""
    return get_project_config_dir(project_root) / filename
