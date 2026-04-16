"""C4 architecture domain models."""

from __future__ import annotations

from enum import Enum

from pydantic import computed_field

from forktex.models.base import ForkTexModel, Identifiable, Tagged


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


class Technology(ForkTexModel):
    name: str
    version: str = ""
    category: TechCategory | None = None


class Port(ForkTexModel):
    host: int
    container: int
    protocol: str = "TCP"


class Dependency(ForkTexModel):
    name: str
    version: str = ""
    category: str = ""


class HealthCheck(ForkTexModel):
    path: str
    interval: int = 30


class Relationship(ForkTexModel):
    source_id: str
    target_id: str
    description: str = ""
    protocol: str = ""
    tags: list[str] = []


class Component(Identifiable, Tagged):
    """C4 Level 4."""

    technology: list[Technology] = []
    files: list[str] = []

    @computed_field
    @property
    def element_type(self) -> str:
        return "component"

    @computed_field
    @property
    def tech_summary(self) -> str:
        return ", ".join(t.name for t in self.technology) if self.technology else ""


class Container(Identifiable, Tagged):
    """C4 Level 3."""

    service_type: ServiceType = ServiceType.COMPUTE
    technology: list[Technology] = []
    ports: list[Port] = []
    image: str = ""
    health: HealthCheck | None = None
    dependencies: list[Dependency] = []
    components: list[Component] = []
    relationships: list[Relationship] = []
    manifest_id: str = ""

    @computed_field
    @property
    def element_type(self) -> str:
        return "container"

    @computed_field
    @property
    def tech_summary(self) -> str:
        return ", ".join(t.name for t in self.technology) if self.technology else ""

    @computed_field
    @property
    def is_database(self) -> bool:
        return self.service_type == ServiceType.PERSISTENCE

    @computed_field
    @property
    def primary_port(self) -> int | None:
        return self.ports[0].host if self.ports else None

    def component_by_id(self, cid: str) -> Component | None:
        return next((c for c in self.components if c.id == cid), None)


class SoftwareSystem(Identifiable, Tagged):
    """C4 Level 2."""

    containers: list[Container] = []
    relationships: list[Relationship] = []
    api_version: str = ""
    provider: str = ""
    region: str = ""
    deploy_strategy: str = ""
    domains: list[str] = []
    fsd_level: str = "L0"

    @computed_field
    @property
    def element_type(self) -> str:
        return "system"

    def container_by_id(self, cid: str) -> Container | None:
        return next((c for c in self.containers if c.id == cid), None)

    @computed_field
    @property
    def compute_containers(self) -> list[Container]:
        return [c for c in self.containers if c.service_type == ServiceType.COMPUTE]

    @computed_field
    @property
    def persistence_containers(self) -> list[Container]:
        return [c for c in self.containers if c.service_type == ServiceType.PERSISTENCE]


class ExternalSystem(Identifiable, Tagged):
    @computed_field
    @property
    def element_type(self) -> str:
        return "external_system"


class Person(Identifiable, Tagged):
    @computed_field
    @property
    def element_type(self) -> str:
        return "person"


class Workspace(Identifiable):
    """C4 Level 1."""

    systems: list[SoftwareSystem] = []
    external_systems: list[ExternalSystem] = []
    persons: list[Person] = []
    relationships: list[Relationship] = []

    def system_by_id(self, sid: str) -> SoftwareSystem | None:
        return next((s for s in self.systems if s.id == sid), None)

    @computed_field
    @property
    def all_ports(self) -> list[dict]:
        ports = []
        for sys in self.systems:
            for ctr in sys.containers:
                for port in ctr.ports:
                    ports.append(
                        {
                            "system": sys.name,
                            "container": ctr.name,
                            "host_port": port.host,
                            "container_port": port.container,
                            "type": ctr.service_type.value,
                        }
                    )
        return sorted(ports, key=lambda p: p["host_port"])
