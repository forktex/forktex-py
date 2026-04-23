"""Typed forktex.json manifest models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field, computed_field

from forktex.fsd.models import ResolveRule
from forktex.models.base import ForkTexModel


MANIFEST_VERSION = "1.0.0"


class AtomOverride(ForkTexModel):
    """Per-atom FSD override declared in forktex.json.

    May also be used to declare a *custom* atom (one that is not in the
    FSD standard catalog) by setting both ``commands`` and ``description``.
    Custom atoms get rendered into the generated Makefile alongside the
    standard atoms, sourced from the keys under ``fsd.atoms`` in forktex.json.
    """

    disabled: bool = False
    reason: str = ""
    description: str = ""
    resolve: list[ResolveRule] = []
    targets: list[str] = []
    aliases: list[str] = []
    commands: list[str] = []
    scope: str | None = None


class FSDConfig(ForkTexModel):
    """Project-level FSD configuration under ``forktex.json.fsd``."""

    version: str | None = Field(
        None,
        alias="version",
        validation_alias=AliasChoices("version", "standardVersion"),
    )
    profiles: list[str] = []
    target_level: str | None = Field(None, alias="targetLevel")
    skip: list[str] = []
    atoms: dict[str, AtomOverride] = {}
    standard_path: str | None = Field(None, alias="standardPath")


class MetadataDef(ForkTexModel):
    """Project metadata for deployment-shaped manifests."""

    name: str
    environment: str = "production"
    project_id: str | None = Field(None, alias="projectId")


class ServiceDef(ForkTexModel):
    """A service in the project."""

    id: str
    type: Literal["compute", "persistence", "observability"] = "compute"
    image: str = ""
    port: int | None = None
    health_path: str | None = Field(None, alias="healthPath")
    replicas: int = 1
    route_prefix: str | None = Field(None, alias="routePrefix")
    description: str = ""
    environment: dict[str, str] = {}
    command: str | None = None
    volumes: list[str] = []
    environments: list[str] | None = None
    dev_only: bool = Field(False, alias="devOnly")
    prod_only: bool = Field(False, alias="prodOnly")
    healthcheck: dict[str, Any] | None = None


class InfrastructureDef(ForkTexModel):
    """Target infrastructure for deployment."""

    provider: str = ""
    flavour: str = ""
    region: str = ""
    image: str = ""


class DeploymentDef(ForkTexModel):
    """Deployment strategy and parameters."""

    strategy: str = "blue-green"
    drain_delay_seconds: int = Field(5, alias="drainDelaySeconds")
    graceful_stop_seconds: int = Field(30, alias="gracefulStopSeconds")
    health_retries: int = Field(30, alias="healthRetries")
    router: str = "haproxy"
    image_strategy: str | None = Field(None, alias="imageStrategy")
    registry: dict[str, Any] = {}


class GatewayDomain(ForkTexModel):
    """A domain entry."""

    host: str
    primary: bool = False


class SSLConfig(ForkTexModel):
    """SSL/TLS configuration for the gateway."""

    enabled: bool = True
    provider: Literal["letsencrypt", "custom", "none"] = "letsencrypt"
    challenge: str = "dns-01"
    dns_provider: str | None = Field(None, alias="dnsProvider")
    email: str = ""
    cert_path: str | None = Field(None, alias="certPath")
    key_path: str | None = Field(None, alias="keyPath")


class GatewayDef(ForkTexModel):
    """Gateway configuration."""

    domains: list[GatewayDomain | str] = []
    ssl: SSLConfig | None = None


class ObservabilityDef(ForkTexModel):
    """Observability feature flags."""

    enabled: bool = False
    logging: dict[str, Any] = {}
    metrics: dict[str, Any] = {}


class PackageDef(ForkTexModel):
    """A publishable package within the project."""

    name: str
    path: str = "."
    version: str = "0.1.0"
    publishable: bool = False
    language: str = "python"
    registry: str = ""
    description: str = ""


class CloudManifestDef(ForkTexModel):
    """Cloud-specific deployment data under ``forktex.json.cloud``."""

    api_version: str | None = Field(None, alias="apiVersion")
    kind: str | None = None
    metadata: MetadataDef | None = None
    infrastructure: InfrastructureDef | None = None
    deployment: DeploymentDef | None = None
    gateway: GatewayDef | None = None
    services: list[ServiceDef] = []
    observability: ObservabilityDef | None = None


class ForktexManifest(ForkTexModel):
    """Universal project manifest — the typed definition of forktex.json."""

    manifest_version: str = Field(MANIFEST_VERSION, alias="manifestVersion")
    api_version: str | None = Field(None, alias="apiVersion")
    kind: str | None = None
    metadata: MetadataDef | None = None

    name: str | None = None
    version: str | None = None
    description: str | None = None

    infrastructure: InfrastructureDef | None = None
    deployment: DeploymentDef | None = None
    gateway: GatewayDef | None = None
    services: list[ServiceDef] = []
    observability: ObservabilityDef | None = None
    packages: list[PackageDef] = []
    fsd: FSDConfig | None = None
    cloud: CloudManifestDef | None = None

    @computed_field
    @property
    def project_name(self) -> str:
        if self.cloud and self.cloud.metadata:
            return self.cloud.metadata.name
        if self.metadata:
            return self.metadata.name
        return self.name or ""

    @computed_field
    @property
    def is_deployment(self) -> bool:
        return bool((self.cloud and self.cloud.kind) or self.kind)

    def service_by_id(self, sid: str) -> ServiceDef | None:
        services = self.cloud.services if self.cloud else self.services
        return next((s for s in services if s.id == sid), None)

    def compute_services(self) -> list[ServiceDef]:
        services = self.cloud.services if self.cloud else self.services
        return [s for s in services if s.type == "compute"]

    def persistence_services(self) -> list[ServiceDef]:
        services = self.cloud.services if self.cloud else self.services
        return [s for s in services if s.type == "persistence"]

    @computed_field
    @property
    def primary_domain(self) -> str | None:
        gateway = self.cloud.gateway if self.cloud else self.gateway
        if not gateway or not gateway.domains:
            return None
        d = gateway.domains[0]
        return d.host if isinstance(d, GatewayDomain) else d

    @classmethod
    def load(cls, path: Path) -> ForktexManifest:
        if not path.is_file():
            raise FileNotFoundError(f"Manifest not found: {path}")
        raw = json.loads(path.read_text())
        raw.setdefault("manifestVersion", MANIFEST_VERSION)
        cloud_raw = raw.get("cloud")
        if cloud_raw is None:
            cloud_keys = (
                "apiVersion",
                "kind",
                "metadata",
                "infrastructure",
                "deployment",
                "gateway",
                "services",
                "observability",
            )
            if any(key in raw for key in cloud_keys):
                cloud_raw = {key: raw.pop(key) for key in cloud_keys if key in raw}
                raw["cloud"] = cloud_raw
        if cloud_raw and "gateway" in cloud_raw and "domains" in cloud_raw["gateway"]:
            cloud_raw["gateway"]["domains"] = [
                {"host": d, "primary": False} if isinstance(d, str) else d
                for d in cloud_raw["gateway"]["domains"]
            ]
        return cls.model_validate(raw)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
