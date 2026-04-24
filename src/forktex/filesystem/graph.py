"""Filesystem knowledge graph for project structure discovery."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from forktex_cloud import paths as _cloud_paths

from forktex.core.paths import FORKTEX_MANIFEST


SKIP_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    _cloud_paths.PROJECT_DIRNAME,
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".expo",
}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_pyproject(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _count_lines(root: Path) -> int:
    total = 0
    for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx"):
        for file_path in root.rglob(ext):
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            try:
                total += len(
                    file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                )
            except OSError:
                continue
    return total


@dataclass
class PackageNode:
    id: str
    name: str
    version: str
    description: str
    rel_path: str
    manifest_path: str
    pyproject_path: str = ""
    publishable: bool = False
    language: str = "python"
    has_makefile: bool = False


@dataclass
class DomainNode:
    id: str
    name: str
    rel_path: str
    line_count: int = 0
    has_makefile: bool = False
    manifest_path: str = ""


@dataclass
class ProjectGraph:
    root: Path
    root_manifest_path: Path
    packages: list[PackageNode] = field(default_factory=list)
    domains: list[DomainNode] = field(default_factory=list)
    child_manifest_paths: list[Path] = field(default_factory=list)


def _package_node_from_paths(
    project_root: Path,
    *,
    package_name: str,
    rel_path: str,
    base_data: dict,
    child_manifest_path: Path | None,
) -> PackageNode:
    package_dir = (project_root / rel_path).resolve()
    child_data = (
        _load_json(child_manifest_path)
        if child_manifest_path and child_manifest_path.exists()
        else {}
    )
    pyproject_path = package_dir / "pyproject.toml"
    pyproject = _load_pyproject(pyproject_path) if pyproject_path.exists() else {}
    project_meta = pyproject.get("project", {})

    name = (
        child_data.get("name")
        or base_data.get("name")
        or project_meta.get("name")
        or package_name
    )
    version = (
        child_data.get("version")
        or base_data.get("version")
        or project_meta.get("version")
        or ""
    )
    description = (
        child_data.get("description")
        or base_data.get("description")
        or project_meta.get("description")
        or ""
    )
    language = base_data.get("language") or (
        "python" if pyproject_path.exists() else ""
    )
    publishable = bool(base_data.get("publishable", True))

    manifest_path = (
        child_manifest_path
        if child_manifest_path and child_manifest_path.exists()
        else project_root / FORKTEX_MANIFEST
    )
    rel_manifest_path = str(manifest_path.relative_to(project_root))
    rel_pyproject_path = (
        str(pyproject_path.relative_to(project_root)) if pyproject_path.exists() else ""
    )

    return PackageNode(
        id=name,
        name=name,
        version=version,
        description=description,
        rel_path=rel_path,
        manifest_path=rel_manifest_path,
        pyproject_path=rel_pyproject_path,
        publishable=publishable,
        language=language or "python",
        has_makefile=(package_dir / "Makefile").exists(),
    )


def _discover_child_manifests(project_root: Path) -> list[Path]:
    child_manifests: list[Path] = []
    for manifest_path in sorted(project_root.rglob(FORKTEX_MANIFEST)):
        if manifest_path == project_root / FORKTEX_MANIFEST:
            continue
        if any(part in SKIP_DIRS for part in manifest_path.parts):
            continue
        child_manifests.append(manifest_path)
    return child_manifests


def _discover_domains(project_root: Path) -> list[DomainNode]:
    root_pkg = project_root / "src" / "forktex"
    if not root_pkg.is_dir():
        return []

    domains: list[DomainNode] = []
    for child in sorted(root_pkg.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name in SKIP_DIRS:
            continue
        domains.append(
            DomainNode(
                id=child.name,
                name=child.name,
                rel_path=str(child.relative_to(project_root)),
                line_count=_count_lines(child),
                has_makefile=(child / "Makefile").exists(),
                manifest_path=str((child / FORKTEX_MANIFEST).relative_to(project_root))
                if (child / FORKTEX_MANIFEST).exists()
                else "",
            )
        )
    return domains


def build_project_graph(project_root: Path) -> ProjectGraph:
    """Build a structural project graph from root + nested manifests."""

    project_root = project_root.resolve()
    root_manifest_path = project_root / FORKTEX_MANIFEST
    root_manifest = _load_json(root_manifest_path)
    child_manifests = _discover_child_manifests(project_root)
    child_by_dir = {path.parent.resolve(): path for path in child_manifests}

    packages: list[PackageNode] = []
    seen_paths: set[str] = set()

    for entry in root_manifest.get("packages", []):
        rel_path = entry.get("path", ".")
        packages.append(
            _package_node_from_paths(
                project_root,
                package_name=entry.get("name", rel_path),
                rel_path=rel_path,
                base_data=entry,
                child_manifest_path=child_by_dir.get(
                    (project_root / rel_path).resolve()
                ),
            )
        )
        seen_paths.add(rel_path)

    for child_manifest_path in child_manifests:
        rel_path = str(child_manifest_path.parent.relative_to(project_root))
        if rel_path in seen_paths:
            continue
        child_data = _load_json(child_manifest_path)
        packages.append(
            _package_node_from_paths(
                project_root,
                package_name=child_data.get("name", child_manifest_path.parent.name),
                rel_path=rel_path,
                base_data=child_data,
                child_manifest_path=child_manifest_path,
            )
        )
        seen_paths.add(rel_path)

    domains = _discover_domains(project_root)
    return ProjectGraph(
        root=project_root,
        root_manifest_path=root_manifest_path,
        packages=packages,
        domains=domains,
        child_manifest_paths=child_manifests,
    )
