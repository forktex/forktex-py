"""FSD Architecture Auto-Discovery — build C4 model from project files.

Discovery sources:
  forktex.json          → L2 containers (cloud services), metadata (provider, region, domains)
  forktex.json packages → Publishable packages (SDKs, libraries)
  forktex.local.json    → L2 host ports
  pyproject.toml        → L2 technology, L3 dependencies
  package.json          → L2 technology, L3 dependencies
  filesystem (app/)     → L3 components (Python packages, routers, engines)
  .git/                 → Git branch, last commit, dirty status
  Makefile              → FSD level
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from forktex.agent.fsd.arch import (
    Component, Container, Dependency, FileNode, GitInfo,
    HealthCheck, PackageInfo, Port, Relationship, ServiceType,
    SoftwareSystem, TechCategory, Technology, Workspace,
)
from forktex.agent.fsd.standard import determine_level
from forktex.agent.fsd.check import _find_makefile_targets, _discover_services
from forktex.core.paths import FORKTEX_LOCAL_MANIFEST, get_manifest_path, has_manifest
from forktex.filesystem.graph import build_project_graph


# ── Git Discovery ────────────────────────────────────────────────────────────


def _discover_git(project_root: Path) -> Optional[GitInfo]:
    """Read git metadata from a project directory."""
    if not (project_root / ".git").exists():
        return None

    def _git(cmd: list[str]) -> str:
        try:
            return subprocess.run(
                ["git"] + cmd, capture_output=True, text=True,
                cwd=str(project_root), timeout=5,
            ).stdout.strip()
        except Exception:
            return ""

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    last_hash = _git(["log", "-1", "--format=%H"])
    last_msg = _git(["log", "-1", "--format=%s"])
    last_date = _git(["log", "-1", "--format=%ci"])
    dirty = bool(_git(["status", "--porcelain"]))
    remote = _git(["config", "--get", "remote.origin.url"])

    return GitInfo(
        branch=branch, last_commit_hash=last_hash[:12] if last_hash else "",
        last_commit_msg=last_msg[:80], last_commit_date=last_date,
        dirty=dirty, remote_url=remote,
    )


# ── Package Discovery ────────────────────────────────────────────────────────


def _discover_packages(manifest: dict) -> list[PackageInfo]:
    """Read packages[] from forktex.json manifest."""
    pkgs = []
    for p in manifest.get("packages", []):
        pkgs.append(PackageInfo(
            name=p.get("name", ""),
            path=p.get("path", ""),
            version=p.get("version", ""),
            language=p.get("language", "python"),
            publishable=p.get("publishable", False),
            description=p.get("description", ""),
        ))
    return pkgs


def _components_from_domains(project_root: Path, domains) -> list[Component]:
    components = []
    for domain in domains:
        domain_dir = project_root / domain.rel_path
        components.append(Component(
            id=domain.id,
            name=domain.name,
            description=_infer_component_desc(domain.name),
            technology=[Technology("Python", category=TechCategory.LANGUAGE)],
            files=[p.name for p in sorted(domain_dir.glob("*.py"))[:10]],
            tags=["domain"],
            file_tree=_build_file_tree(domain_dir, max_depth=2),
            line_count=domain.line_count,
        ))
    return components


def _discover_package_containers(project_root: Path, graph) -> tuple[list[Container], list[PackageInfo]]:
    containers: list[Container] = []
    packages: list[PackageInfo] = []
    for package in graph.packages:
        package_dir = project_root / package.rel_path
        techs = _detect_tech_from_dir(package_dir)
        deps = _read_deps(package_dir) if package_dir.is_dir() else []
        if package.rel_path == ".":
            components = _components_from_domains(project_root, graph.domains)
        else:
            components = _discover_components(package_dir) if package_dir.is_dir() else []

        container_id = package.name.replace(" ", "-").replace("/", "-")
        containers.append(Container(
            id=container_id,
            name=package.name,
            description=package.description or f"{package.name} package",
            service_type=ServiceType.COMPUTE,
            technology=techs,
            dependencies=deps,
            components=components,
            tags=["Package"],
            manifest_id=container_id,
        ))
        packages.append(PackageInfo(
            name=package.name,
            path=package.rel_path,
            version=package.version,
            language=package.language,
            publishable=package.publishable,
            description=package.description,
            manifest_path=package.manifest_path,
        ))
    return containers, packages


# ── Filesystem Tree Discovery ────────────────────────────────────────────────


def _build_file_tree(root: Path, max_depth: int = 3, _depth: int = 0) -> FileNode:
    """Build a filesystem tree rooted at a directory, with line counts."""
    node = FileNode(name=root.name, path=str(root), is_dir=root.is_dir())

    if root.is_dir() and _depth < max_depth:
        for child in sorted(root.iterdir()):
            if child.name.startswith((".", "__pycache__", "node_modules", ".git")):
                continue
            if child.is_dir():
                child_node = _build_file_tree(child, max_depth, _depth + 1)
                node.children.append(child_node)
            elif child.suffix in (".py", ".ts", ".tsx", ".js", ".jsx"):
                try:
                    lines = len(child.read_text(encoding="utf-8", errors="ignore").splitlines())
                except OSError:
                    lines = 0
                node.children.append(FileNode(
                    name=child.name, path=str(child),
                    is_dir=False, size=child.stat().st_size,
                    line_count=lines,
                ))
    elif root.is_file():
        try:
            node.line_count = len(root.read_text(encoding="utf-8", errors="ignore").splitlines())
            node.size = root.stat().st_size
        except OSError:
            pass

    return node


def _count_lines(directory: Path) -> int:
    """Count total lines of code in Python/TS files under a directory."""
    total = 0
    for ext in ("*.py", "*.ts", "*.tsx"):
        for f in directory.rglob(ext):
            if "__pycache__" in str(f) or "node_modules" in str(f):
                continue
            try:
                total += len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
            except OSError:
                pass
    return total


# ── Technology Detection ─────────────────────────────────────────────────────

IMAGE_TECH: dict[str, tuple[str, TechCategory]] = {
    "postgres": ("PostgreSQL", TechCategory.DATABASE),
    "redis": ("Redis", TechCategory.CACHE),
    "minio": ("MinIO", TechCategory.STORAGE),
    "qdrant": ("Qdrant", TechCategory.VECTOR_DB),
    "nginx": ("Nginx", TechCategory.PROXY),
    "mailhog": ("MailHog", TechCategory.MAIL),
    "loki": ("Loki", TechCategory.OBSERVABILITY),
    "promtail": ("Promtail", TechCategory.OBSERVABILITY),
    "node": ("Node.js", TechCategory.RUNTIME),
}


def _detect_tech_from_image(image: str) -> list[Technology]:
    techs = []
    for key, (name, cat) in IMAGE_TECH.items():
        if key in image.lower():
            version = image.split(":")[-1] if ":" in image else None
            techs.append(Technology(name, version, cat))
    return techs


def _detect_tech_from_dir(d: Path) -> list[Technology]:
    techs = []
    pyproject = d / "pyproject.toml"
    requirements = d / "requirements.txt"

    if pyproject.exists():
        content = pyproject.read_text()
        techs.append(Technology("Python", category=TechCategory.LANGUAGE))
        if "fastapi" in content.lower():
            techs.append(Technology("FastAPI", category=TechCategory.FRAMEWORK))
        if "sqlalchemy" in content.lower():
            techs.append(Technology("SQLAlchemy", category=TechCategory.FRAMEWORK))
        if "[tool.poetry" in content:
            techs.append(Technology("Poetry", category=TechCategory.PACKAGE_MANAGER))
    elif requirements.exists():
        content = requirements.read_text().lower()
        techs.append(Technology("Python", category=TechCategory.LANGUAGE))
        if "fastapi" in content:
            techs.append(Technology("FastAPI", category=TechCategory.FRAMEWORK))
        techs.append(Technology("pip", category=TechCategory.PACKAGE_MANAGER))

    pkg_json = d / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            techs.append(Technology("TypeScript" if "typescript" in deps else "JavaScript", category=TechCategory.LANGUAGE))
            if "react-native" in deps:
                techs.append(Technology("React Native", category=TechCategory.FRAMEWORK))
            elif "react" in deps:
                techs.append(Technology("React", category=TechCategory.FRAMEWORK))
            if "expo" in deps or "expo-router" in deps:
                techs.append(Technology("Expo", category=TechCategory.FRAMEWORK))
            if "next" in deps:
                techs.append(Technology("Next.js", category=TechCategory.FRAMEWORK))
            techs.append(Technology("pnpm", category=TechCategory.PACKAGE_MANAGER))
        except (json.JSONDecodeError, KeyError):
            pass

    return techs


def _read_deps(d: Path, limit: int = 20) -> list[Dependency]:
    deps = []
    pyproject = d / "pyproject.toml"
    if pyproject.exists():
        in_deps = False
        for line in pyproject.read_text().splitlines():
            if "[tool.poetry.dependencies]" in line or "dependencies = [" in line:
                in_deps = True
                continue
            if in_deps:
                if line.startswith("[") or line.strip() == "]":
                    break
                line = line.strip().strip(",").strip('"')
                if "=" in line or ">=" in line:
                    parts = line.split("=", 1) if "=" in line else line.split(">=", 1)
                    name = parts[0].strip().strip('"').strip("'")
                    version = parts[1].strip().strip('"').strip("'") if len(parts) > 1 else ""
                    if name and name != "python":
                        deps.append(Dependency(name, version))
            if len(deps) >= limit:
                break

    pkg_json = d / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            for name, ver in list(pkg.get("dependencies", {}).items())[:limit]:
                deps.append(Dependency(name, ver))
        except (json.JSONDecodeError, KeyError):
            pass

    return deps[:limit]


# ── C4 Level 3: Component Discovery ─────────────────────────────────────────

def _discover_components(service_dir: Path) -> list[Component]:
    """Discover L3 components from a service's filesystem.

    For Python services: look for packages under app/ (api/, engine/, schemas/, etc.)
    For JS services: look for directories under src/ (components/, store/, api/, etc.)
    """
    components = []

    # Python: app/ subdirectories
    app_dir = service_dir / "app"
    if app_dir.is_dir():
        for d in sorted(app_dir.iterdir()):
            if d.is_dir() and not d.name.startswith(("__", ".")):
                py_files = list(d.glob("*.py"))
                if py_files:
                    components.append(Component(
                        id=d.name,
                        name=d.name,
                        description=_infer_component_desc(d.name),
                        technology=[Technology("Python", category=TechCategory.LANGUAGE)],
                        files=[f.name for f in py_files[:10]],
                        file_tree=_build_file_tree(d, max_depth=2),
                        line_count=_count_lines(d),
                    ))

    # JavaScript/TypeScript: src/ subdirectories
    src_dir = service_dir / "src"
    if src_dir.is_dir():
        for d in sorted(src_dir.iterdir()):
            if d.is_dir() and not d.name.startswith((".", "node_modules")):
                ts_files = list(d.glob("*.ts")) + list(d.glob("*.tsx"))
                if ts_files:
                    components.append(Component(
                        id=d.name,
                        name=d.name,
                        description=_infer_component_desc(d.name),
                        technology=[Technology("TypeScript", category=TechCategory.LANGUAGE)],
                        files=[f.name for f in ts_files[:10]],
                        file_tree=_build_file_tree(d, max_depth=2),
                        line_count=_count_lines(d),
                    ))

    return components


COMPONENT_DESCRIPTIONS = {
    "api": "HTTP routes and request handlers",
    "engine": "Business logic and service layer",
    "schemas": "Request/response data models",
    "database": "ORM models and database access",
    "models": "Data models",
    "auth": "Authentication and authorization",
    "core": "Core utilities and configuration",
    "services": "Service orchestration",
    "infra": "Infrastructure integration",
    "secrets": "Secret management",
    "providers": "Provider integrations and context providers",
    "dns": "DNS management",
    "ssl": "SSL/TLS certificate management",
    "bridge": "Manifest-to-infrastructure bridge",
    "components": "UI components",
    "store": "State management (Redux)",
    "theme": "Theming and styling",
    "utils": "Shared utilities",
    "hooks": "React hooks",
}


def _infer_component_desc(name: str) -> str:
    return COMPONENT_DESCRIPTIONS.get(name, f"{name} module")


# ── Project Discovery ────────────────────────────────────────────────────────

def discover_project(project_root: Path) -> SoftwareSystem:
    """Build a full C4 model for a project from its files."""
    manifest_path = get_manifest_path(project_root)
    local_path = project_root / FORKTEX_LOCAL_MANIFEST
    graph = build_project_graph(project_root)

    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    local = json.loads(local_path.read_text()) if local_path.exists() else {}

    # Metadata
    cloud_manifest = manifest.get("cloud", manifest)
    meta = cloud_manifest.get("metadata", {})
    infra = cloud_manifest.get("infrastructure", {})
    deploy = cloud_manifest.get("deployment", {})
    gateway = cloud_manifest.get("gateway", {})

    project_name = meta.get("name") or manifest.get("name", project_root.name)
    domains = []
    for d in gateway.get("domains", []):
        if isinstance(d, dict):
            domains.append(d.get("host", ""))
        elif isinstance(d, str):
            domains.append(d)

    # Merge services
    local_svcs = {s["id"]: s for s in local.get("services", [])}
    containers = []
    relationships = []
    compute_ids = []
    persistence_ids = []

    for svc_def in cloud_manifest.get("services", []):
        sid = svc_def["id"]
        svc_type_str = svc_def.get("type", "compute")
        svc_type = ServiceType(svc_type_str) if svc_type_str in [e.value for e in ServiceType] else ServiceType.COMPUTE

        local_svc = local_svcs.get(sid, {})
        image = local_svc.get("image", svc_def.get("image", ""))
        port = local_svc.get("port", svc_def.get("port", 0))
        host_port = local_svc.get("hostPort", port)
        health_path = svc_def.get("healthPath")

        # Technology
        techs = _detect_tech_from_image(image)
        svc_dir = project_root / sid
        if svc_dir.is_dir():
            techs.extend(_detect_tech_from_dir(svc_dir))

        # Ports
        ports = []
        if host_port and port:
            ports.append(Port(host=host_port, container=port))
        elif host_port:
            ports.append(Port(host=host_port, container=host_port))

        # Health
        health = HealthCheck(path=health_path) if health_path else None

        # Dependencies
        deps = _read_deps(svc_dir) if svc_dir.is_dir() else []

        # Components (L3)
        components = _discover_components(svc_dir) if svc_dir.is_dir() else []

        # Tags
        tags = ["Database"] if any(t.category == TechCategory.DATABASE for t in techs) else []

        container = Container(
            id=sid, name=sid, description=svc_def.get("description", f"{sid} service"),
            service_type=svc_type, technology=techs, ports=ports, image=image,
            health=health, dependencies=deps, components=components,
            tags=tags, manifest_id=sid,
        )
        containers.append(container)

        if svc_type == ServiceType.COMPUTE:
            compute_ids.append(sid)
        elif svc_type == ServiceType.PERSISTENCE:
            persistence_ids.append(sid)

    # Auto-relationships: compute → persistence
    for cid in compute_ids:
        for pid in persistence_ids:
            relationships.append(Relationship(cid, pid, "Reads/Writes", "TCP"))

    if not containers:
        containers, packages = _discover_package_containers(project_root, graph)
    else:
        packages = [
            PackageInfo(
                name=p.name,
                path=p.rel_path,
                version=p.version,
                language=p.language,
                publishable=p.publishable,
                description=p.description,
                manifest_path=p.manifest_path,
            )
            for p in graph.packages
        ]

    # FSD level
    all_targets = _find_makefile_targets(project_root / "Makefile")
    for svc_info in _discover_services(project_root):
        for t in svc_info["targets"]:
            all_targets.add(f"{svc_info['name']}-{t}")
            all_targets.add(t)
    fsd_level = determine_level(all_targets)

    # Git info
    git_info = _discover_git(project_root)

    return SoftwareSystem(
        id=project_root.name, name=project_name, description=f"{project_name} platform",
        containers=containers, relationships=relationships,
        api_version=cloud_manifest.get("apiVersion"),
        provider=infra.get("provider"),
        region=infra.get("region"),
        deploy_strategy=deploy.get("strategy"),
        domains=domains,
        fsd_level=fsd_level,
        git=git_info,
        packages=packages,
    )


def _discover_library_edges(base_dir: Path) -> list[Relationship]:
    """Read library dependency edges from docs/engineering/libraries.json."""
    libs_path = base_dir / "docs" / "engineering" / "libraries.json"
    if not libs_path.exists():
        return []

    try:
        data = json.loads(libs_path.read_text(encoding="utf-8"))
        edges = data.get("dependency_graph", {}).get("edges", [])
        return [
            Relationship(source_id=src, target_id=tgt, description="depends on", tags=["library"])
            for src, tgt in edges
        ]
    except (json.JSONDecodeError, OSError):
        return []


def discover_multi(base_dir: Path, project_names: list[str] | None = None) -> Workspace:
    """Discover across multiple projects."""
    if project_names:
        dirs = [base_dir / n for n in project_names if has_manifest(base_dir / n)]
    else:
        dirs = sorted(d for d in base_dir.iterdir() if d.is_dir() and has_manifest(d))

    systems = []
    for d in dirs:
        try:
            systems.append(discover_project(d))
        except Exception:
            pass

    # Cross-system dependency edges from libraries.json
    library_edges = _discover_library_edges(base_dir)

    return Workspace(
        name=base_dir.name if base_dir.name else "Workspace",
        description="C4 model — auto-discovered from project files",
        systems=systems,
        relationships=library_edges,
    )
