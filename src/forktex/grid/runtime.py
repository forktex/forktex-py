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

"""Runtime wiring for the grid persistence backend.

Closes the loop with the cloud SDK's existing compose pipeline: forktex-py's
own ``forktex.json`` declares a ``db`` (postgres) persistence service, and
``forktex grid up`` reuses ``forktex_cloud`` to generate + run
``.forktex/docker-compose.local.yml`` — the same path as ``forktex cloud up
--env local``. The grid app then connects to that Postgres via a
``DATABASE_URL`` derived from the manifest.

All ``forktex_cloud`` / Docker access is lazy so this module imports without
the ``[api]`` extra or a container runtime present.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_DB_SERVICE = "db"


def project_root() -> Path:
    """The project root (nearest ancestor with ``forktex.json``), else cwd."""
    try:
        from forktex.core.paths import find_project_root

        root = find_project_root()
        if root:
            return Path(root)
    except Exception:
        pass
    return Path.cwd()


def _resolve_secret(value: Any) -> str:
    """Resolve a manifest secret. ``${vault:...}`` refs fall back to an env var.

    For local POC the password is a literal; production secrets stay in the
    vault and are injected by the cloud pipeline, not here.
    """
    if isinstance(value, str) and value.startswith("${vault:"):
        return os.environ.get("FORKTEX_DB_PASSWORD", "forktex")
    return str(value)


def database_url_from_services(
    services: list[dict[str, Any]],
    *,
    service_id: str = DEFAULT_DB_SERVICE,
    host: str = "127.0.0.1",
) -> str | None:
    """Derive an asyncpg ``DATABASE_URL`` from a manifest's persistence services.

    Pure (no SDK / Docker) so it's unit-testable. Uses the service's host-facing
    port (``hostPort`` if mapped, else ``port``) and POSTGRES_* env.
    """
    for svc in services:
        if svc.get("id") == service_id and svc.get("type") == "persistence":
            env = svc.get("environment") or {}
            user = env.get("POSTGRES_USER", "forktex")
            database = env.get("POSTGRES_DB", "forktex")
            password = _resolve_secret(env.get("POSTGRES_PASSWORD", "forktex"))
            port = (
                svc.get("hostPort") or svc.get("host_port") or svc.get("port") or 5432
            )
            return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
    return None


def derive_database_url(root: Path | None = None) -> str | None:
    """``DATABASE_URL`` env wins; otherwise derive from the local manifest.

    Returns ``None`` when neither is available — callers then fall back to the
    embedded ``pgserver`` (zero-Docker dev/tests).
    """
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    root = root or project_root()
    try:
        from forktex_cloud.manifest.loader import Manifest  # type: ignore[import-not-found]

        manifest = Manifest.load(root / "forktex.json", env="local")
        return database_url_from_services(manifest.persistence_services())
    except Exception:
        return None


def ensure_docker() -> None:
    """Preflight: Docker + Compose v2 must be present (clear hint if not)."""
    if shutil.which("docker") is None:
        raise RuntimeError(
            "Docker is required for 'forktex grid up'. Install it: https://docs.docker.com/get-docker/"
        )
    try:
        subprocess.run(
            ["docker", "compose", "version"], check=True, capture_output=True
        )
    except Exception as exc:
        raise RuntimeError(
            "'docker compose' (Compose v2) is unavailable — update Docker."
        ) from exc


def _compose(root: Path) -> tuple[str, str]:
    """Generate the local compose file; return (project_name, compose_file)."""
    from forktex.cloud.compose import write_local_compose
    from forktex_cloud.manifest.loader import Manifest  # type: ignore[import-not-found]

    manifest = Manifest.load(root / "forktex.json", env="local")
    compose_file = str(write_local_compose(manifest, root, observability=False))
    return (manifest.name or "forktex", compose_file)


def compose_up(root: Path | None = None, *, detach: bool = True) -> str:
    """Bring up the Dockerized Postgres (and any compute services). Returns DATABASE_URL."""
    root = root or project_root()
    ensure_docker()
    project, compose_file = _compose(root)
    cmd = ["docker", "compose", "-p", project, "-f", compose_file, "up"]
    if detach:
        cmd.append("-d")
    subprocess.run(cmd, check=True)
    return derive_database_url(root) or ""


def compose_down(root: Path | None = None, *, volumes: bool = False) -> None:
    root = root or project_root()
    ensure_docker()
    project, compose_file = _compose(root)
    cmd = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        compose_file,
        "down",
        "--remove-orphans",
    ]
    if volumes:
        cmd.append("-v")
    subprocess.run(cmd, check=True)


def compose_status(root: Path | None = None) -> None:
    root = root or project_root()
    ensure_docker()
    project, compose_file = _compose(root)
    subprocess.run(
        ["docker", "compose", "-p", project, "-f", compose_file, "ps"], check=False
    )


__all__ = [
    "DEFAULT_DB_SERVICE",
    "project_root",
    "database_url_from_services",
    "derive_database_url",
    "ensure_docker",
    "compose_up",
    "compose_down",
    "compose_status",
]
