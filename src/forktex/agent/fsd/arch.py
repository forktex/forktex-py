"""FSD Architecture Model — C4 typed hierarchy.

Strongly typed Python model mapping to C4 levels, rooted in forktex.json:

  C4 Level 1 (Context)    → Workspace: the full view, systems + external systems
  C4 Level 2 (Container)  → SoftwareSystem: one project, services from forktex.json
  C4 Level 3 (Component)  → Container: one service, internal modules from filesystem
  C4 Level 4 (Code)       → Component: one module, classes/functions (future)

Each level is navigable — you can drill into a system to see its containers,
into a container to see its components. The UI renders the current level and
allows in/out navigation.

The Structurizr DSL, JSON, and HTML are all projections of this same typed model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Enums ────────────────────────────────────────────────────────────────────


class ElementType(str, Enum):
    """C4 element types."""

    PERSON = "person"
    SOFTWARE_SYSTEM = "softwareSystem"
    CONTAINER = "container"
    COMPONENT = "component"
    EXTERNAL_SYSTEM = "externalSystem"


class ServiceType(str, Enum):
    COMPUTE = "compute"
    PERSISTENCE = "persistence"
    OBSERVABILITY = "observability"


class TechCategory(str, Enum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    CACHE = "cache"
    STORAGE = "storage"
    VECTOR_DB = "vector_db"
    PROXY = "proxy"
    MAIL = "mail"
    OBSERVABILITY = "observability"
    RUNTIME = "runtime"
    PACKAGE_MANAGER = "package_manager"


# ── Value Objects ────────────────────────────────────────────────────────────


@dataclass
class Technology:
    name: str
    version: Optional[str] = None
    category: TechCategory = TechCategory.FRAMEWORK


@dataclass
class Port:
    host: int
    container: int
    protocol: str = "tcp"


@dataclass
class Dependency:
    name: str
    version: str
    category: str = "runtime"


@dataclass
class HealthCheck:
    path: Optional[str] = None
    interval: str = "30s"


@dataclass
class Relationship:
    """A directed relationship between two elements."""

    source_id: str
    target_id: str
    description: str
    protocol: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class GitInfo:
    """Git metadata for a project."""

    branch: str = ""
    last_commit_hash: str = ""
    last_commit_msg: str = ""
    last_commit_date: str = ""
    dirty: bool = False
    remote_url: str = ""


@dataclass
class PackageInfo:
    """A publishable library artifact (from forktex.json packages[])."""

    name: str
    path: str
    version: str = ""
    language: str = "python"
    publishable: bool = False
    description: str = ""
    manifest_path: str = ""


@dataclass
class FileNode:
    """A node in the filesystem tree for deep component inspection."""

    name: str
    path: str
    is_dir: bool = False
    size: int = 0
    children: list["FileNode"] = field(default_factory=list)
    line_count: int = 0


# ── C4 Elements (hierarchical) ──────────────────────────────────────────────


@dataclass
class Component:
    """C4 Level 4 — a module/package within a container (e.g., api/app/engine/)."""

    id: str
    name: str
    description: str
    technology: list[Technology] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    file_tree: Optional[FileNode] = None  # Deep filesystem tree
    line_count: int = 0  # Total lines of code

    @property
    def element_type(self) -> ElementType:
        return ElementType.COMPONENT

    @property
    def tech_summary(self) -> str:
        return ", ".join(t.name for t in self.technology) if self.technology else ""


@dataclass
class Container:
    """C4 Level 3 — a service within a system (maps to forktex.json services[])."""

    id: str
    name: str
    description: str
    service_type: ServiceType
    technology: list[Technology] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)
    image: Optional[str] = None
    health: Optional[HealthCheck] = None
    dependencies: list[Dependency] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    # Source: which field in forktex.json this came from
    manifest_id: Optional[str] = None  # the "id" field in forktex.json services[]

    @property
    def element_type(self) -> ElementType:
        return ElementType.CONTAINER

    @property
    def tech_summary(self) -> str:
        return (
            ", ".join(t.name for t in self.technology) if self.technology else "unknown"
        )

    @property
    def is_database(self) -> bool:
        return any(t.category == TechCategory.DATABASE for t in self.technology)

    @property
    def primary_port(self) -> Optional[Port]:
        return self.ports[0] if self.ports else None

    def component_by_id(self, cid: str) -> Optional[Component]:
        return next((c for c in self.components if c.id == cid), None)


@dataclass
class SoftwareSystem:
    """C4 Level 2 — a project/platform (maps to one forktex.json)."""

    id: str
    name: str
    description: str
    containers: list[Container] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    # Metadata from forktex.json
    api_version: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    deploy_strategy: Optional[str] = None
    domains: list[str] = field(default_factory=list)

    # FSD
    fsd_level: str = "L0"

    # Git
    git: Optional[GitInfo] = None

    # Packages (from forktex.json packages[])
    packages: list[PackageInfo] = field(default_factory=list)

    @property
    def element_type(self) -> ElementType:
        return ElementType.SOFTWARE_SYSTEM

    def container_by_id(self, cid: str) -> Optional[Container]:
        return next((c for c in self.containers if c.id == cid), None)

    @property
    def compute_containers(self) -> list[Container]:
        return [c for c in self.containers if c.service_type == ServiceType.COMPUTE]

    @property
    def persistence_containers(self) -> list[Container]:
        return [c for c in self.containers if c.service_type == ServiceType.PERSISTENCE]


@dataclass
class ExternalSystem:
    """An external dependency (e.g., OpenAI, Stripe, Cloudflare)."""

    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)

    @property
    def element_type(self) -> ElementType:
        return ElementType.EXTERNAL_SYSTEM


@dataclass
class Person:
    """A user/actor in the system context."""

    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)

    @property
    def element_type(self) -> ElementType:
        return ElementType.PERSON


@dataclass
class Workspace:
    """C4 Level 1 — the full context view. Root of the hierarchy."""

    name: str
    description: str
    systems: list[SoftwareSystem] = field(default_factory=list)
    external_systems: list[ExternalSystem] = field(default_factory=list)
    persons: list[Person] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)

    def system_by_id(self, sid: str) -> Optional[SoftwareSystem]:
        return next((s for s in self.systems if s.id == sid), None)

    @property
    def all_ports(self) -> list[dict]:
        result = []
        for sys in self.systems:
            for c in sys.containers:
                for p in c.ports:
                    result.append(
                        {
                            "system": sys.name,
                            "system_id": sys.id,
                            "service": c.id,
                            "host_port": p.host,
                            "container_port": p.container,
                            "type": c.service_type.value,
                        }
                    )
        return sorted(result, key=lambda x: x["host_port"])

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Full JSON-serializable representation (all C4 levels)."""
        return {
            "name": self.name,
            "description": self.description,
            "systems": [_system_dict(s) for s in self.systems],
            "external_systems": [
                {"id": e.id, "name": e.name, "description": e.description}
                for e in self.external_systems
            ],
            "persons": [
                {"id": p.id, "name": p.name, "description": p.description}
                for p in self.persons
            ],
            "relationships": [_rel_dict(r) for r in self.relationships],
            "port_allocation": self.all_ports,
        }

    def to_navigation(self) -> dict:
        """Hierarchical navigation structure for interactive UI.

        Returns a tree where each node has:
        - id, name, type, level (c4 level number)
        - children (next level down)
        - data (level-specific details like ports, tech, etc.)
        """
        return {
            "id": "root",
            "name": self.name,
            "type": "workspace",
            "level": 1,
            "children": [
                {
                    "id": sys.id,
                    "name": sys.name,
                    "type": "system",
                    "level": 2,
                    "data": {
                        "fsd_level": sys.fsd_level,
                        "provider": sys.provider,
                        "region": sys.region,
                        "deploy_strategy": sys.deploy_strategy,
                        "domains": sys.domains,
                    },
                    "children": [
                        {
                            "id": f"{sys.id}.{c.id}",
                            "name": c.name,
                            "type": "container",
                            "level": 3,
                            "data": {
                                "service_type": c.service_type.value,
                                "technology": [
                                    {
                                        "name": t.name,
                                        "version": t.version,
                                        "category": t.category.value,
                                    }
                                    for t in c.technology
                                ],
                                "ports": [
                                    {"host": p.host, "container": p.container}
                                    for p in c.ports
                                ],
                                "image": c.image,
                                "health_path": c.health.path if c.health else None,
                                "dep_count": len(c.dependencies),
                            },
                            "children": [
                                {
                                    "id": f"{sys.id}.{c.id}.{comp.id}",
                                    "name": comp.name,
                                    "type": "component",
                                    "level": 4,
                                    "data": {
                                        "description": comp.description,
                                        "technology": comp.tech_summary,
                                        "files": comp.files[:5],
                                    },
                                    "children": [],
                                }
                                for comp in c.components
                            ],
                        }
                        for c in sys.containers
                    ],
                }
                for sys in self.systems
            ],
        }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _system_dict(sys: SoftwareSystem) -> dict:
    return {
        "id": sys.id,
        "name": sys.name,
        "description": sys.description,
        "fsd_level": sys.fsd_level,
        "api_version": sys.api_version,
        "provider": sys.provider,
        "region": sys.region,
        "deploy_strategy": sys.deploy_strategy,
        "domains": sys.domains,
        "git": _git_dict(sys.git) if sys.git else None,
        "packages": [_package_dict(p) for p in sys.packages],
        "containers": [_container_dict(c) for c in sys.containers],
        "relationships": [_rel_dict(r) for r in sys.relationships],
    }


def _git_dict(g: GitInfo) -> dict:
    return {
        "branch": g.branch,
        "last_commit": g.last_commit_hash,
        "message": g.last_commit_msg,
        "date": g.last_commit_date,
        "dirty": g.dirty,
        "remote": g.remote_url,
    }


def _package_dict(p: PackageInfo) -> dict:
    return {
        "name": p.name,
        "path": p.path,
        "version": p.version,
        "language": p.language,
        "publishable": p.publishable,
        "description": p.description,
        "manifest_path": p.manifest_path,
    }


def _file_tree_dict(node: FileNode) -> dict:
    d: dict = {"name": node.name, "path": node.path, "is_dir": node.is_dir}
    if node.is_dir:
        d["children"] = [_file_tree_dict(c) for c in node.children]
    else:
        d["size"] = node.size
        d["lines"] = node.line_count
    return d


def _container_dict(c: Container) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "service_type": c.service_type.value,
        "technology": [
            {"name": t.name, "version": t.version, "category": t.category.value}
            for t in c.technology
        ],
        "ports": [{"host": p.host, "container": p.container} for p in c.ports],
        "image": c.image,
        "health_path": c.health.path if c.health else None,
        "dependencies": [
            {"name": d.name, "version": d.version} for d in c.dependencies
        ],
        "components": [_component_dict(comp) for comp in c.components],
        "tags": c.tags,
    }


def _component_dict(comp: Component) -> dict:
    d: dict = {
        "id": comp.id,
        "name": comp.name,
        "description": comp.description,
        "technology": comp.tech_summary,
        "files": comp.files,
        "line_count": comp.line_count,
    }
    if comp.file_tree:
        d["file_tree"] = _file_tree_dict(comp.file_tree)
    return d


def _rel_dict(r: Relationship) -> dict:
    return {
        "source": r.source_id,
        "target": r.target_id,
        "description": r.description,
        "protocol": r.protocol,
    }


# ── Structurizr DSL Generator ────────────────────────────────────────────────


def to_structurizr_dsl(workspace: Workspace) -> str:
    """Generate Structurizr DSL from the typed workspace model."""
    lines = [
        f'workspace "{workspace.name}" "{workspace.description}" {{',
        "",
        "    model {",
        "        !identifiers hierarchical",
        "",
    ]

    # Persons
    for p in workspace.persons:
        lines.append(f'        {_dsl_id(p.id)} = person "{p.name}" "{p.description}"')
    if workspace.persons:
        lines.append("")

    # Systems
    for sys in workspace.systems:
        sid = _dsl_id(sys.id)
        lines.append(
            f'        {sid} = softwareSystem "{sys.name}" "{sys.description}" {{'
        )
        for c in sys.containers:
            cid = _dsl_id(c.id)
            tech = c.tech_summary
            tags_str = ""
            if c.is_database:
                tags_str = ' {\n                tags "Database"\n            }'
            lines.append(
                f'            {cid} = container "{c.name}" "{c.description}" "{tech}"{tags_str}'
            )

            # Components within container
            for comp in c.components:
                comp_id = _dsl_id(comp.id)
                lines.append(
                    f'                {comp_id} = component "{comp.name}" "{comp.description}" "{comp.tech_summary}"'
                )

        lines.append("        }")
        lines.append("")

    # External systems
    for ext in workspace.external_systems:
        lines.append(
            f'        {_dsl_id(ext.id)} = softwareSystem "{ext.name}" "{ext.description}"'
        )
    if workspace.external_systems:
        lines.append("")

    # Relationships within systems
    for sys in workspace.systems:
        sid = _dsl_id(sys.id)
        for rel in sys.relationships:
            src = f"{sid}.{_dsl_id(rel.source_id)}"
            tgt = f"{sid}.{_dsl_id(rel.target_id)}"
            proto = f' "{rel.protocol}"' if rel.protocol else ""
            lines.append(f'        {src} -> {tgt} "{rel.description}"{proto}')

    # Cross-system relationships
    for rel in workspace.relationships:
        proto = f' "{rel.protocol}"' if rel.protocol else ""
        lines.append(
            f'        {_dsl_id(rel.source_id)} -> {_dsl_id(rel.target_id)} "{rel.description}"{proto}'
        )

    lines.extend(["    }", ""])

    # Views
    lines.append("    views {")
    # L1: System context
    if len(workspace.systems) > 1:
        lines.extend(
            [
                "        systemLandscape {",
                "            include *",
                "            autolayout lr",
                "        }",
            ]
        )

    # L2: Container per system
    for sys in workspace.systems:
        sid = _dsl_id(sys.id)
        lines.extend(
            [
                f"        container {sid} {{",
                "            include *",
                "            autolayout lr",
                "        }",
            ]
        )

    # L3: Component per container (if any have components)
    for sys in workspace.systems:
        sid = _dsl_id(sys.id)
        for c in sys.containers:
            if c.components:
                lines.extend(
                    [
                        f"        component {sid}.{_dsl_id(c.id)} {{",
                        "            include *",
                        "            autolayout lr",
                        "        }",
                    ]
                )

    # Styles
    lines.extend(
        [
            "",
            "        styles {",
            '            element "Person" { shape Person\n                background #0b3c5d\n                color #ffffff }',
            '            element "Software System" { background #6c6c6c\n                color #ffffff }',
            '            element "Container" { background #2a7fc1\n                color #ffffff }',
            '            element "Database" { shape Cylinder\n                background #1a6d3a\n                color #ffffff }',
            '            element "Component" { background #4a90d9\n                color #ffffff }',
            '            relationship "Relationship" { color #707070\n                thickness 2 }',
            "        }",
        ]
    )

    lines.extend(["    }", "}"])
    return "\n".join(lines)


def _dsl_id(s: str) -> str:
    return s.replace("-", "_").replace(".", "_").replace(" ", "_")
