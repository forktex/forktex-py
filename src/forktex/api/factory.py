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


from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from forktex.api.middleware import ExceptionEnvelopeMiddleware, SecurityHeadersMiddleware
from forktex.log import TraceIDMiddleware, get_logger
from forktex.types import BaseAppModel

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


class LivenessResponse(BaseAppModel):
    status: str = "ok"


class ReadinessResponse(BaseAppModel):
    status: str
    checks: dict[str, bool] = Field(default_factory=dict)


HealthProbe = Callable[[], Awaitable[bool]]
"""A coroutine returning ``True`` when the dependency is reachable.

Used by ``/health/ready``. The probe should be fast (≤200ms) and
side-effect-free; readiness checks fire on every probe call."""


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = "ForkTex Service"
    version: str = "1.0.0"
    description: str = ""
    debug: bool = False

    api_prefix: str = ""

    @field_validator("api_prefix")
    @classmethod
    def _check_api_prefix(cls, value: str) -> str:
        if value and (not value.startswith("/") or value.endswith("/")):
            raise ValueError("api_prefix must start with '/' and not end with one, e.g. '/api'")
        return value

    enable_trace_id: bool = True
    enable_security_headers: bool = True
    enable_exception_handler: bool = True
    handle_unexpected: bool = True

    cors_origins: list[str] | None = None
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    lifespan: Callable[[Any], Any] | None = None

    readiness_probes: dict[str, HealthProbe] = Field(default_factory=dict)
    readiness_timeout: float = 5.0


def create_app(config: AppConfig | None = None) -> FastAPI:
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
    except ImportError as exc:
        raise ImportError("Install 'forktex[api]' (fastapi) to use forktex.api") from exc

    cfg = config or AppConfig()

    prefix = cfg.api_prefix

    app = FastAPI(
        title=cfg.title,
        version=cfg.version,
        description=cfg.description,
        debug=cfg.debug,
        lifespan=cfg.lifespan,
        docs_url=f"{prefix}/docs",
        redoc_url=f"{prefix}/redoc",
        openapi_url=f"{prefix}/openapi.json",
        swagger_ui_oauth2_redirect_url=f"{prefix}/docs/oauth2-redirect",
    )

    if cfg.enable_exception_handler:
        app.add_middleware(ExceptionEnvelopeMiddleware, handle_unexpected=cfg.handle_unexpected)
    if cfg.enable_trace_id:
        app.add_middleware(TraceIDMiddleware)
    if cfg.cors_origins is not None:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_credentials=cfg.cors_allow_credentials,
            allow_methods=cfg.cors_allow_methods,
            allow_headers=cfg.cors_allow_headers,
        )
    if cfg.enable_security_headers:
        app.add_middleware(SecurityHeadersMiddleware)

    @app.get(f"{prefix}/health", tags=["health"])
    async def _liveness() -> LivenessResponse:
        return LivenessResponse()

    @app.get(f"{prefix}/health/ready", tags=["health"], response_model=None)
    async def _readiness() -> JSONResponse:
        async def _check(name: str, probe: HealthProbe) -> bool:
            try:
                return bool(await asyncio.wait_for(probe(), timeout=cfg.readiness_timeout))
            except TimeoutError:
                logger.warning(
                    "readiness probe timed out",
                    extra={"probe": name, "timeout": cfg.readiness_timeout},
                )
                return False
            except Exception:
                logger.exception("readiness probe raised", extra={"probe": name})
                return False

        names = list(cfg.readiness_probes)
        outcomes = await asyncio.gather(*(_check(n, cfg.readiness_probes[n]) for n in names))
        results = dict(zip(names, outcomes, strict=True))
        ok = all(results.values())
        if not ok:
            logger.warning(
                "service not ready",
                extra={"failing": sorted(n for n, passed in results.items() if not passed)},
            )
        body = ReadinessResponse(status="ready" if ok else "not_ready", checks=results)
        return JSONResponse(status_code=200 if ok else 503, content=body.model_dump())

    return app


__all__ = ["AppConfig", "HealthProbe", "LivenessResponse", "ReadinessResponse", "create_app"]
