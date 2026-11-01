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

from uuid import uuid7

from forktex import iso
from forktex.error import AppError, AppErrorCode, BadRequestError
from starlette.requests import Request
from collections.abc import AsyncIterator
from fastapi.responses import JSONResponse
from starlette.types import Receive, Scope, Send
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from forktex.api import AppConfig, SecurityHeadersMiddleware, create_app
from forktex.api.middleware import ExceptionEnvelopeMiddleware, _http_status_for
from forktex.error import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableEntityError,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_every_error_code_maps_to_a_status() -> None:
    unmapped = []
    for code in AppErrorCode:
        error = AppError("x")
        error.code = code
        if _http_status_for(error) == 500 and code not in {AppErrorCode.INTERNAL, AppErrorCode.FAILED}:
            unmapped.append(code.name)
    assert unmapped == [], f"AppErrorCode members with no explicit status: {unmapped}"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (NotFoundError("nope"), 404),
        (UnprocessableEntityError("bad"), 422),
        (ForbiddenError("no"), 403),
        (ConflictError("clash"), 409),
    ],
)
def test_known_errors_map_to_their_status(error: AppError, expected: int) -> None:
    assert _http_status_for(error) == expected


def test_unknown_custom_code_falls_back_to_500() -> None:

    class ServiceSpecificError(AppError):
        code = "my_service_specific_code"

    assert _http_status_for(ServiceSpecificError("boom")) == 500


def test_liveness_is_ok() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_with_no_probes_is_ready() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_readiness_reports_each_probe() -> None:
    async def up() -> bool:
        return True

    async def down() -> bool:
        return False

    app = create_app(AppConfig(readiness_probes={"db": up, "cache": down}))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"db": True, "cache": False}}


def test_a_raising_probe_is_not_ready_rather_than_a_500() -> None:

    async def broken() -> bool:
        raise RuntimeError("connection refused")

    app = create_app(AppConfig(readiness_probes={"db": broken}))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"db": False}


def _app_that_raises(exc: BaseException, **config: object) -> FastAPI:
    app = create_app(AppConfig(**config))

    @app.get("/boom")
    async def _boom() -> None:
        raise exc

    return app


def test_app_error_becomes_an_envelope_with_its_status() -> None:
    with TestClient(_app_that_raises(NotFoundError("order 7 not found"))) as client:
        response = client.get("/boom")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == AppErrorCode.NOT_FOUND.value
    assert body["message"] == "order 7 not found"


def test_envelope_is_camel_case_on_the_wire() -> None:
    with TestClient(_app_that_raises(NotFoundError("x"))) as client:
        response = client.get("/boom")

    assert "traceId" in response.json()
    assert "trace_id" not in response.json()


def test_trace_id_in_the_envelope_matches_the_response_header() -> None:
    with TestClient(_app_that_raises(NotFoundError("x"))) as client:
        response = client.get("/boom", headers={"X-Request-ID": "req-abc-123"})

    assert response.headers["X-Request-ID"] == "req-abc-123"
    assert response.json()["traceId"] == "req-abc-123"


def test_trace_id_is_minted_when_the_client_sends_none() -> None:
    with TestClient(_app_that_raises(NotFoundError("x"))) as client:
        response = client.get("/boom")

    assert response.json()["traceId"] == response.headers["X-Request-ID"]
    assert response.json()["traceId"]


def test_unexpected_error_becomes_a_generic_500_that_leaks_nothing() -> None:
    with TestClient(_app_that_raises(RuntimeError("password=hunter2 at db.py:42"))) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert "hunter2" not in response.text
    assert body["message"] == "Internal Server Error"
    assert body["code"] == AppErrorCode.INTERNAL.value


def test_handle_unexpected_false_lets_the_error_propagate() -> None:
    app = _app_that_raises(RuntimeError("boom"), handle_unexpected=False)
    with TestClient(app, raise_server_exceptions=True) as client, pytest.raises(RuntimeError, match="boom"):
        client.get("/boom")


def test_app_error_is_still_enveloped_when_handle_unexpected_is_off() -> None:
    app = _app_that_raises(NotFoundError("gone"), handle_unexpected=False)
    with TestClient(app) as client:
        response = client.get("/boom")
    assert response.status_code == 404


def test_exception_handler_can_be_disabled_entirely() -> None:
    app = _app_that_raises(NotFoundError("gone"), enable_exception_handler=False)
    with TestClient(app, raise_server_exceptions=True) as client, pytest.raises(AppError):
        client.get("/boom")


def test_fastapi_validation_handling_is_left_untouched() -> None:
    app = create_app()

    @app.get("/items")
    async def _items(count: int) -> dict[str, int]:
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/items", params={"count": "not-an-int"})
    assert response.status_code == 422


def test_security_headers_are_present_on_a_success() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    for header, value in SecurityHeadersMiddleware.DEFAULT_HEADERS.items():
        assert response.headers[header] == value


def test_security_headers_are_present_on_an_error_response() -> None:
    with TestClient(_app_that_raises(NotFoundError("x"))) as client:
        response = client.get("/boom")
    assert response.status_code == 404
    assert response.headers["X-Frame-Options"] == "DENY"


def test_security_headers_do_not_clobber_one_the_app_set() -> None:
    app = create_app()

    @app.get("/framed")
    async def _framed() -> JSONResponse:
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True}, headers={"X-Frame-Options": "SAMEORIGIN"})

    with TestClient(app) as client:
        response = client.get("/framed")
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_security_headers_can_be_disabled() -> None:
    with TestClient(create_app(AppConfig(enable_security_headers=False))) as client:
        response = client.get("/health")
    assert "X-Frame-Options" not in response.headers


def test_no_cors_headers_when_origins_are_unset() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_is_installed_when_origins_are_set() -> None:
    app = create_app(AppConfig(cors_origins=["https://app.test"]))
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "https://app.test"})
    assert response.headers["access-control-allow-origin"] == "https://app.test"


def test_cors_preflight_still_carries_security_headers() -> None:
    app = create_app(AppConfig(cors_origins=["https://app.test"]))
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "https://app.test",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_trace_id_can_be_disabled() -> None:
    with TestClient(create_app(AppConfig(enable_trace_id=False))) as client:
        response = client.get("/health")
    assert "X-Request-ID" not in response.headers


def test_custom_title_and_version_reach_the_openapi_document() -> None:
    app = create_app(AppConfig(title="Orders API", version="2.1.0", description="Order management"))
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "Orders API"
    assert schema["info"]["version"] == "2.1.0"


def test_lifespan_is_passed_through() -> None:
    from contextlib import asynccontextmanager

    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        events.append("startup")
        yield
        events.append("shutdown")

    with TestClient(create_app(AppConfig(lifespan=lifespan))) as client:
        client.get("/health")

    assert events == ["startup", "shutdown"]


async def test_middleware_passes_non_http_scopes_straight_through() -> None:
    seen: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    for cls in (ExceptionEnvelopeMiddleware, SecurityHeadersMiddleware):
        await cls(app)({"type": "websocket"}, None, None)

    assert seen == ["websocket", "websocket"]


def test_middleware_are_usable_on_a_plain_asgi_app_without_create_app() -> None:
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def boom(_request: Request) -> None:
        raise NotFoundError("standalone")

    async def fine(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/boom", boom), Route("/fine", fine)])
    app.add_middleware(ExceptionEnvelopeMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    with TestClient(app) as client:
        assert client.get("/fine").headers["X-Frame-Options"] == "DENY"
        error = client.get("/boom")
    assert error.status_code == 404
    assert error.json()["message"] == "standalone"


def test_downstream_package_errors_render_with_their_real_status() -> None:
    from forktex.cache.errors import CacheUnreachableError
    from forktex.database.errors import TransactionBoundaryError
    from forktex.storage.errors import ObjectNotFoundError

    cases = [
        (ObjectNotFoundError("object 'a/b.png' is absent"), 404),
        (CacheUnreachableError("redis is unreachable"), 503),
        (TransactionBoundaryError("commit() is not available here"), 500),
    ]
    for error, expected_status in cases:
        with TestClient(_app_that_raises(error)) as client:
            response = client.get("/boom")
        assert response.status_code == expected_status, f"{type(error).__name__} → {response.status_code}"
        assert response.json()["message"] == error.message


def test_trace_id_covers_background_tasks() -> None:
    from starlette.background import BackgroundTask
    from starlette.responses import JSONResponse

    from forktex.log import get_trace_id

    seen: dict[str, str | None] = {}
    app = create_app()

    @app.get("/bg", response_model=None)
    async def _bg() -> JSONResponse:
        return JSONResponse(
            {"in_request": get_trace_id()},
            background=BackgroundTask(lambda: seen.__setitem__("bg", get_trace_id())),
        )

    with TestClient(app) as client:
        response = client.get("/bg", headers={"X-Request-ID": "trace-BG"})

    assert response.json()["in_request"] == "trace-BG"
    assert seen["bg"] == "trace-BG"


@pytest.mark.parametrize("error", [NotFoundError("too late"), RuntimeError("too late")])
def test_error_raised_after_the_response_started_is_re_raised(error: BaseException) -> None:
    from starlette.responses import StreamingResponse

    app = create_app()

    @app.get("/stream", response_model=None)
    async def _stream() -> StreamingResponse:
        async def body() -> AsyncIterator[bytes]:
            yield b"partial"
            raise error

        return StreamingResponse(body(), media_type="text/plain")

    with TestClient(app, raise_server_exceptions=True) as client, pytest.raises(type(error), match="too late"):
        client.get("/stream")


def test_readiness_rejects_a_non_callable_probe() -> None:
    with pytest.raises(Exception, match="readiness_probes"):
        AppConfig(readiness_probes={"db": "not-a-callable"})


def test_a_hanging_probe_is_bounded_by_the_readiness_timeout() -> None:
    import asyncio

    async def hangs() -> bool:
        await asyncio.sleep(30)
        return True

    app = create_app(AppConfig(readiness_probes={"db": hangs}, readiness_timeout=0.1))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"db": False}


def test_probes_run_concurrently_not_in_sequence() -> None:
    import asyncio
    import time

    async def slow() -> bool:
        await asyncio.sleep(0.15)
        return True

    probes = {f"dep{i}": slow for i in range(4)}
    app = create_app(AppConfig(readiness_probes=probes, readiness_timeout=5.0))

    with TestClient(app) as client:
        started = time.monotonic()
        response = client.get("/health/ready")
        elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 0.4, f"probes appear to run in sequence ({elapsed:.2f}s for 4 x 0.15s)"


def test_a_slow_probe_does_not_mask_a_healthy_one() -> None:
    import asyncio

    async def fast() -> bool:
        return True

    async def hangs() -> bool:
        await asyncio.sleep(30)
        return True

    app = create_app(AppConfig(readiness_probes={"cache": fast, "db": hangs}, readiness_timeout=0.2))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"cache": True, "db": False}


def test_by_default_everything_mounts_at_the_root() -> None:
    client = TestClient(create_app())

    assert client.get("/health").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_api_prefix_moves_health_and_docs_together() -> None:
    client = TestClient(create_app(AppConfig(api_prefix="/api")))

    for path in ("/api/health", "/api/health/ready", "/api/docs", "/api/openapi.json"):
        assert client.get(path).status_code == 200, path

    for path in ("/health", "/docs", "/openapi.json", "/docs/oauth2-redirect"):
        assert client.get(path).status_code == 404, path


def test_api_prefix_is_reflected_in_the_contract() -> None:
    app = create_app(AppConfig(api_prefix="/api"))

    assert sorted(app.openapi()["paths"]) == ["/api/health", "/api/health/ready"]


@pytest.mark.parametrize("bad", ["api", "/api/", "/"])
def test_a_malformed_prefix_is_rejected_at_config_time(bad: str) -> None:
    with pytest.raises(ValidationError):
        AppConfig(api_prefix=bad)


def test_an_unknown_config_field_is_rejected_rather_than_ignored() -> None:
    with pytest.raises(ValidationError, match="not_a_real_setting"):
        AppConfig(not_a_real_setting="/api")


def test_an_error_envelope_survives_details_that_are_not_json_native() -> None:
    """A UUID or datetime in `details` crashed the middleware's own response, so a
    deliberate 400 reached the client as a plain-text 500 with no traceId."""
    error = BadRequestError("bad", details={"id": uuid7(), "when": iso.now()})
    with TestClient(_app_that_raises(error)) as client:
        response = client.get("/boom")

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == AppErrorCode.BAD_REQUEST.value
    assert isinstance(body["details"]["id"], str)
    assert isinstance(body["details"]["when"], str)
    assert body["traceId"]
