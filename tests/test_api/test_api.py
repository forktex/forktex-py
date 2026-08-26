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


"""`forktex.api` — the FastAPI factory, its middleware stack, and health probes.

Driven through fastapi's TestClient (a real ASGI round trip) rather than by
calling the middleware objects directly: the contracts that matter here are
ordering ones — that `traceId` in an error body equals the `X-Request-ID`
header, that security headers survive an error response — and only a real
request exercises them.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from forktex.api import AppConfig, SecurityHeadersMiddleware, create_app
from forktex.api.middleware import ExceptionEnvelopeMiddleware, _http_status_for
from forktex.error import (
    AppError,
    AppErrorCode,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableEntityError,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# --------------------------------------------------------------------------
# status mapping
# --------------------------------------------------------------------------


def test_every_error_code_maps_to_a_status():
    """The mapping is exhaustive over the vocabulary: a new `AppErrorCode` member
    silently falling through to 500 is the failure this guards."""
    unmapped = []
    for code in AppErrorCode:
        error = AppError("x")
        error.code = code  # `code` is a class attribute; override per-instance to probe
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
def test_known_errors_map_to_their_status(error: AppError, expected: int):
    assert _http_status_for(error) == expected


def test_unknown_custom_code_falls_back_to_500():
    """`AppError.code` is typed as the enum but documented as an open `str`, and a
    service may define its own. It must degrade to 500, not raise."""

    class ServiceSpecificError(AppError):
        code = "my_service_specific_code"  # type: ignore[assignment]

    assert _http_status_for(ServiceSpecificError("boom")) == 500


# --------------------------------------------------------------------------
# health probes
# --------------------------------------------------------------------------


def test_liveness_is_ok():
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_with_no_probes_is_ready():
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_readiness_reports_each_probe():
    async def up() -> bool:
        return True

    async def down() -> bool:
        return False

    app = create_app(AppConfig(readiness_probes={"db": up, "cache": down}))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"db": True, "cache": False}}


def test_a_raising_probe_is_not_ready_rather_than_a_500():
    """A probe that raises is "not ready", not a crashed endpoint — otherwise an
    orchestrator's readiness check cannot distinguish the two."""

    async def broken() -> bool:
        raise RuntimeError("connection refused")

    app = create_app(AppConfig(readiness_probes={"db": broken}))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"db": False}


# --------------------------------------------------------------------------
# error envelope
# --------------------------------------------------------------------------


def _app_that_raises(exc: BaseException, **config: object) -> FastAPI:
    app = create_app(AppConfig(**config))  # type: ignore[arg-type]

    @app.get("/boom")
    async def _boom() -> None:
        raise exc

    return app


def test_app_error_becomes_an_envelope_with_its_status():
    with TestClient(_app_that_raises(NotFoundError("order 7 not found"))) as client:
        response = client.get("/boom")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == AppErrorCode.NOT_FOUND.value
    assert body["message"] == "order 7 not found"


def test_envelope_is_camel_case_on_the_wire():
    """`BaseAppModel` sets `serialize_by_alias`, so the envelope's `trace_id` field
    must appear as `traceId` — a snake_case key here is a wire-contract break."""
    with TestClient(_app_that_raises(NotFoundError("x"))) as client:
        response = client.get("/boom")

    assert "traceId" in response.json()
    assert "trace_id" not in response.json()


def test_trace_id_in_the_envelope_matches_the_response_header():
    """The ordering contract: `ExceptionEnvelopeMiddleware` must run INSIDE
    `TraceIDMiddleware`, whose context manager resets the contextvar on exit. If
    the two are swapped, `traceId` comes back null."""
    with TestClient(_app_that_raises(NotFoundError("x"))) as client:
        response = client.get("/boom", headers={"X-Request-ID": "req-abc-123"})

    assert response.headers["X-Request-ID"] == "req-abc-123"
    assert response.json()["traceId"] == "req-abc-123"


def test_trace_id_is_minted_when_the_client_sends_none():
    with TestClient(_app_that_raises(NotFoundError("x"))) as client:
        response = client.get("/boom")

    assert response.json()["traceId"] == response.headers["X-Request-ID"]
    assert response.json()["traceId"]


def test_unexpected_error_becomes_a_generic_500_that_leaks_nothing():
    with TestClient(_app_that_raises(RuntimeError("password=hunter2 at db.py:42"))) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert "hunter2" not in response.text
    assert body["message"] == "Internal Server Error"
    assert body["code"] == AppErrorCode.INTERNAL.value


def test_handle_unexpected_false_lets_the_error_propagate():
    """Opting out must genuinely re-raise, so a consumer's own handler (or the
    ASGI server) sees the original exception rather than a swallowed 500."""
    app = _app_that_raises(RuntimeError("boom"), handle_unexpected=False)
    with TestClient(app, raise_server_exceptions=True) as client, pytest.raises(RuntimeError, match="boom"):
        client.get("/boom")


def test_app_error_is_still_enveloped_when_handle_unexpected_is_off():
    """`handle_unexpected` governs only the catch-all — a declared `AppError` is
    the middleware's primary job and must still map."""
    app = _app_that_raises(NotFoundError("gone"), handle_unexpected=False)
    with TestClient(app) as client:
        response = client.get("/boom")
    assert response.status_code == 404


def test_exception_handler_can_be_disabled_entirely():
    app = _app_that_raises(NotFoundError("gone"), enable_exception_handler=False)
    with TestClient(app, raise_server_exceptions=True) as client, pytest.raises(AppError):
        client.get("/boom")


def test_fastapi_validation_handling_is_left_untouched():
    """The middleware must not shadow FastAPI's own 422 for a bad query param."""
    app = create_app()

    @app.get("/items")
    async def _items(count: int) -> dict[str, int]:
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/items", params={"count": "not-an-int"})
    assert response.status_code == 422


# --------------------------------------------------------------------------
# security headers
# --------------------------------------------------------------------------


def test_security_headers_are_present_on_a_success():
    with TestClient(create_app()) as client:
        response = client.get("/health")
    for header, value in SecurityHeadersMiddleware.DEFAULT_HEADERS.items():
        assert response.headers[header] == value


def test_security_headers_are_present_on_an_error_response():
    """Security headers are outermost precisely so they survive an error — an
    envelope response is still a response to a browser."""
    with TestClient(_app_that_raises(NotFoundError("x"))) as client:
        response = client.get("/boom")
    assert response.status_code == 404
    assert response.headers["X-Frame-Options"] == "DENY"


def test_security_headers_do_not_clobber_one_the_app_set():
    app = create_app()

    @app.get("/framed")
    async def _framed():
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True}, headers={"X-Frame-Options": "SAMEORIGIN"})

    with TestClient(app) as client:
        response = client.get("/framed")
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_security_headers_can_be_disabled():
    with TestClient(create_app(AppConfig(enable_security_headers=False))) as client:
        response = client.get("/health")
    assert "X-Frame-Options" not in response.headers


# --------------------------------------------------------------------------
# CORS + trace-id toggles
# --------------------------------------------------------------------------


def test_no_cors_headers_when_origins_are_unset():
    """The documented default: an API-key-only service leaves `cors_origins`
    unset and gets no CORS middleware at all."""
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_is_installed_when_origins_are_set():
    app = create_app(AppConfig(cors_origins=["https://app.test"]))
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "https://app.test"})
    assert response.headers["access-control-allow-origin"] == "https://app.test"


def test_cors_preflight_still_carries_security_headers():
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


def test_trace_id_can_be_disabled():
    with TestClient(create_app(AppConfig(enable_trace_id=False))) as client:
        response = client.get("/health")
    assert "X-Request-ID" not in response.headers


def test_custom_title_and_version_reach_the_openapi_document():
    app = create_app(AppConfig(title="Orders API", version="2.1.0", description="Order management"))
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "Orders API"
    assert schema["info"]["version"] == "2.1.0"


def test_lifespan_is_passed_through():
    """`lifespan` is the hook services use to open/close pools, so a dropped
    passthrough would silently skip every startup step."""
    from contextlib import asynccontextmanager

    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        events.append("startup")
        yield
        events.append("shutdown")

    with TestClient(create_app(AppConfig(lifespan=lifespan))) as client:
        client.get("/health")

    assert events == ["startup", "shutdown"]


# --------------------------------------------------------------------------
# pure-ASGI contract
# --------------------------------------------------------------------------


async def test_middleware_passes_non_http_scopes_straight_through():
    """Both middleware are pure ASGI, so they see lifespan/websocket scopes too —
    a scope-type check is what keeps them from corrupting those."""
    seen: list[str] = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    for cls in (ExceptionEnvelopeMiddleware, SecurityHeadersMiddleware):
        await cls(app)({"type": "websocket"}, None, None)  # type: ignore[arg-type]

    assert seen == ["websocket", "websocket"]


def test_middleware_are_usable_on_a_plain_asgi_app_without_create_app():
    """They are exported so a consumer who does not want the whole factory can
    still take one piece — that only holds if they work standalone."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def boom(_request):
        raise NotFoundError("standalone")

    async def fine(_request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/boom", boom), Route("/fine", fine)])
    app.add_middleware(ExceptionEnvelopeMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    with TestClient(app) as client:
        assert client.get("/fine").headers["X-Frame-Options"] == "DENY"
        error = client.get("/boom")
    assert error.status_code == 404
    assert error.json()["message"] == "standalone"


def test_downstream_package_errors_render_with_their_real_status():
    """Regression guard for the masked-500 bug: `vector` and `graph` once rooted their
    hierarchies at bare `Exception`, so `except AppError` could not match them and every
    one surfaced as a generic 500 with its message masked. They subclass `AppError` now,
    so each must carry its real code through to a real status."""
    from forktex.graph.errors import NodeNotFoundError
    from forktex.vector.errors import CollectionNotFoundError, DimensionMismatchError

    cases = [
        (NodeNotFoundError("node 'a' is absent"), 404),
        (CollectionNotFoundError("collection 'docs' is absent"), 404),
        (DimensionMismatchError("expected 768, got 512"), 422),
    ]
    for error, expected_status in cases:
        with TestClient(_app_that_raises(error)) as client:
            response = client.get("/boom")
        assert response.status_code == expected_status, f"{type(error).__name__} → {response.status_code}"
        # The real message survives — it is not masked as "Internal Server Error".
        # Compared against `.message`, not `str(error)`: `NodeNotFoundError` is also a
        # `KeyError`, whose `__str__` reprs its args and so adds quotes. The envelope
        # reads `.message`, which is why the wire shape stays clean.
        assert response.json()["message"] == error.message


def test_trace_id_covers_background_tasks():
    """`TraceIDMiddleware` scopes the id over the WHOLE ASGI call, so a background task
    (which runs after the response is sent) still logs with it — the case
    `BaseHTTPMiddleware` got wrong, where its reset fired first and the task saw None."""
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
def test_error_raised_after_the_response_started_is_re_raised(error: BaseException):
    """Once `http.response.start` is on the wire the status line is fixed, so an
    envelope cannot replace it. The middleware must re-raise rather than emit a
    second, malformed response."""
    from starlette.responses import StreamingResponse

    app = create_app()

    @app.get("/stream", response_model=None)
    async def _stream() -> StreamingResponse:
        async def body():
            yield b"partial"
            raise error

        return StreamingResponse(body(), media_type="text/plain")

    with TestClient(app, raise_server_exceptions=True) as client, pytest.raises(type(error), match="too late"):
        client.get("/stream")


def test_readiness_rejects_a_non_callable_probe():
    """`AppConfig` validates probes rather than deferring the failure to the first
    readiness call, where it would surface as a 503 with no explanation."""
    with pytest.raises(Exception, match="readiness_probes"):
        AppConfig(readiness_probes={"db": "not-a-callable"})  # type: ignore[dict-item]


def test_a_hanging_probe_is_bounded_by_the_readiness_timeout():
    """A probe with no timeout of its own must not hang the endpoint — an
    orchestrator reading no answer at all cannot tell which dependency stalled."""
    import asyncio

    async def hangs() -> bool:
        await asyncio.sleep(30)
        return True

    app = create_app(AppConfig(readiness_probes={"db": hangs}, readiness_timeout=0.1))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"db": False}


def test_probes_run_concurrently_not_in_sequence():
    """Serial probes made the endpoint's latency the SUM of its dependencies, which
    pushes a multi-dependency service past its own probe deadline."""
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
    # Serial would be ~0.6s; concurrent is ~0.15s. The bound leaves generous slack.
    assert elapsed < 0.4, f"probes appear to run in sequence ({elapsed:.2f}s for 4 x 0.15s)"


def test_a_slow_probe_does_not_mask_a_healthy_one():
    """Under a shared budget the fast probe's real result must still be reported, so
    the response says which dependency is actually at fault."""
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


# --------------------------------------------------------------------------- #
# api_prefix                                                                    #
# --------------------------------------------------------------------------- #


def test_by_default_everything_mounts_at_the_root():
    client = TestClient(create_app())

    assert client.get("/health").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_api_prefix_moves_health_and_docs_together():
    """A gateway that routes /api/* without stripping it can reach the lot."""
    client = TestClient(create_app(AppConfig(api_prefix="/api")))

    for path in ("/api/health", "/api/health/ready", "/api/docs", "/api/openapi.json"):
        assert client.get(path).status_code == 200, path

    # And nothing is left behind at the root to be routed to the wrong service.
    for path in ("/health", "/docs", "/openapi.json", "/docs/oauth2-redirect"):
        assert client.get(path).status_code == 404, path


def test_api_prefix_is_reflected_in_the_contract():
    app = create_app(AppConfig(api_prefix="/api"))

    assert sorted(app.openapi()["paths"]) == ["/api/health", "/api/health/ready"]


@pytest.mark.parametrize("bad", ["api", "/api/", "/"])
def test_a_malformed_prefix_is_rejected_at_config_time(bad: str):
    """Fail where the mistake is, not with a 404 nobody can explain."""
    with pytest.raises(ValidationError):
        AppConfig(api_prefix=bad)


def test_an_unknown_config_field_is_rejected_rather_than_ignored():
    """Version skew must not degrade into a silently different app.

    A service written against a newer forktex and run against an older one used
    to have its setting dropped by pydantic's default `extra="ignore"`, mounting
    routes at paths the service never asked for.
    """
    with pytest.raises(ValidationError, match="not_a_real_setting"):
        AppConfig(not_a_real_setting="/api")
