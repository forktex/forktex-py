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
    healthcheck: dict[str, Any] | None = None


class InfrastructureDef(ForkTexModel):
    """Per-server infrastructure spec — provider sizing + region + OS image.

    V1 multi-server: this is the base for each entry in
    :class:`InfrastructureBundle.servers`. Single-server manifests have one
    entry; multi-server manifests have N entries discriminated by ``id``.
    """

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
    """Legacy pre-V1 domain entry.

    Kept for backward-compat of consumers that imported ``GatewayDomain``
    directly from forktex-py before the V1 multi-server reshape. V1
    manifests use ``gateway.domain: str`` + ``gateway.sans: list[str]`` —
    see :class:`GatewayDef`.
    """

    host: str
    primary: bool = False


class SSLConfig(ForkTexModel):
    """SSL/TLS configuration for the gateway."""

    enabled: bool = True
    provider: Literal["letsencrypt", "zerossl", "custom", "none"] = "letsencrypt"
    challenge: str = "dns-01"
    dns_provider: str | None = Field(None, alias="dnsProvider")
    email: str = ""
    cert_path: str | None = Field(None, alias="certPath")
    key_path: str | None = Field(None, alias="keyPath")
    acme_server: str | None = Field(None, alias="acmeServer")
    eab_kid: str | None = Field(None, alias="eabKid")
    eab_key: str | None = Field(None, alias="eabKey")


class GatewayDef(ForkTexModel):
    """Per-server public-edge configuration (V1 multi-server)."""

    domain: str = ""
    sans: list[str] = []
    ssl: SSLConfig | None = None


class ServerSpec(InfrastructureDef):
    """Multi-server infrastructure entry — extends :class:`InfrastructureDef`
    with ``id``, ``primary``, and per-server ``gateway``.
    """

    id: str = "primary"
    primary: bool = False
    gateway: GatewayDef | None = None


class InfrastructureBundle(ForkTexModel):
    """Container for ``infrastructure.servers[]``."""

    servers: list[ServerSpec] = []


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
    """Cloud-specific deployment data under ``forktex.json.cloud``.

    V1 multi-server: ``infrastructure`` wraps a list of servers, each with
    its own per-server ``gateway``. No top-level ``gateway`` field.
    """

    api_version: str | None = Field(None, alias="apiVersion")
    kind: str | None = None
    metadata: MetadataDef | None = None
    infrastructure: InfrastructureBundle | None = None
    deployment: DeploymentDef | None = None
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
        if self.cloud and self.cloud.infrastructure:
            for srv in self.cloud.infrastructure.servers:
                if srv.primary and srv.gateway:
                    return srv.gateway.domain or None
            if self.cloud.infrastructure.servers:
                gw = self.cloud.infrastructure.servers[0].gateway
                return gw.domain if gw else None
        if self.gateway and self.gateway.domain:
            return self.gateway.domain
        return None

    @classmethod
    def load(cls, path: Path, *, env: str | None = None) -> ForktexManifest:
        """Load a manifest, optionally merging a per-env overlay.

        When ``env`` is provided, looks for ``forktex.<env>.json`` next to
        ``path`` and deep-merges it into the base before validation. Mirrors
        the cloud SDK's ``forktex_cloud.Manifest.load(path, env=...)`` shape
        so the same on-disk convention works across both tools.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Manifest not found: {path}")
        raw = json.loads(path.read_text())
        if env:
            from forktex.manifest._overlay import deep_merge

            overlay_path = path.parent / f"forktex.{env}.json"
            if overlay_path.is_file():
                overlay = json.loads(overlay_path.read_text())
                raw = deep_merge(raw, overlay)
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
        return cls.model_validate(raw)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
