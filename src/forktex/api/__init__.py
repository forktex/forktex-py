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


"""FastAPI application factory — the ``[api]`` extra.

Boilerplate elimination: ``create_app(AppConfig())`` returns a preconfigured
FastAPI instance with the cross-cutting concerns every service otherwise wires
by hand — all opt-in/opt-out via :class:`AppConfig`:

- trace-id propagation (:class:`forktex.log.TraceIDMiddleware` — one
  ``X-Request-ID`` header, correlated with the logs and the error envelope);
- security headers;
- ``AppError`` → ``ErrorEnvelope`` mapping (plus an optional catch-all for
  unexpected errors, so a stack trace never reaches a client);
- CORS (installed only when ``cors_origins`` is set);
- ASGI ``lifespan`` passthrough;
- ``/health`` liveness + ``/health/ready`` readiness probes.

Deliberately left to the consumer, because each is service-specific: rate
limiting / idempotency, auth (tokens, RBAC), and the per-request DB session
(use ``Depends(forktex.database.session_scope)``).

Quickstart::

    from forktex.api import AppConfig, create_app
    from forktex.log import setup_logging

    setup_logging(service="orders")
    app = create_app(AppConfig(title="Orders", version="1.2.0"))

    @app.get("/orders/{order_id}")
    async def get_order(order_id: str) -> dict[str, str]:
        raise NotFoundError(f"order {order_id}")   # → 404 + ErrorEnvelope

Install with ``pip install "forktex[api]"``. Importing this package needs no
FastAPI — only :func:`create_app` does, and it raises ``ImportError`` naming the
extra if it is missing.

``ExceptionEnvelopeMiddleware`` is deliberately not re-exported here: ``create_app``
wires it for you, and a caller assembling their own app reaches it at
``forktex.api.middleware``. Both middleware classes are pure ASGI, so they work on
any ASGI app without ``create_app``.
"""

from forktex.api.factory import (
    AppConfig,
    HealthProbe,
    LivenessResponse,
    ReadinessResponse,
    create_app,
)
from forktex.api.middleware import SecurityHeadersMiddleware

__all__ = [
    "AppConfig",
    "HealthProbe",
    "LivenessResponse",
    "ReadinessResponse",
    "SecurityHeadersMiddleware",
    "create_app",
]
