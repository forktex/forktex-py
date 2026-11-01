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

from starlette.types import Message, Receive, Scope, Send
import pytest

from forktex.log import TraceIDMiddleware, get_root_trace_id, get_trace_id


async def _run_middleware(header_value: bytes | None) -> str | None:
    captured: list[str | None] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        captured.append(get_trace_id())

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        pass

    headers = [(b"x-request-id", header_value)] if header_value is not None else []
    middleware = TraceIDMiddleware(app)
    await middleware({"type": "http", "headers": headers}, receive, send)
    return captured[0]


@pytest.mark.asyncio
async def test_trace_id_middleware_sanitizes_injected_header() -> None:
    trace_id = await _run_middleware(b"abc\n2026-01-01 FAKE LOG LINE")
    assert "\n" not in (trace_id or "")
    assert trace_id != "abc\n2026-01-01 FAKE LOG LINE"


@pytest.mark.asyncio
async def test_trace_id_middleware_accepts_valid_header() -> None:
    trace_id = await _run_middleware(b"req-abc-123")
    assert trace_id == "req-abc-123"


@pytest.mark.asyncio
async def test_trace_id_middleware_mints_uuid_when_header_absent() -> None:
    trace_id = await _run_middleware(None)
    assert trace_id is not None
    assert len(trace_id) == 36


@pytest.mark.asyncio
async def test_trace_id_middleware_echoes_header_on_response() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})

    sent: list[dict] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = TraceIDMiddleware(app)
    await middleware({"type": "http", "headers": [(b"x-request-id", b"req-echo-1")]}, receive, send)

    start_message = sent[0]
    assert start_message["headers"] == [(b"x-request-id", b"req-echo-1")]


@pytest.mark.asyncio
async def test_trace_id_middleware_custom_header_name() -> None:
    captured: list[str | None] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        captured.append(get_trace_id())

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        pass

    middleware = TraceIDMiddleware(app, header="X-Trace-ID")
    await middleware({"type": "http", "headers": [(b"x-trace-id", b"custom-header-value")]}, receive, send)
    assert captured[0] == "custom-header-value"

    captured.clear()
    await middleware({"type": "http", "headers": [(b"x-request-id", b"ignored")]}, receive, send)
    assert captured[0] != "ignored"


@pytest.mark.asyncio
async def test_trace_id_middleware_passes_through_non_http_scopes() -> None:
    calls = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append(scope["type"])

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        pass

    middleware = TraceIDMiddleware(app)
    await middleware({"type": "lifespan"}, receive, send)
    assert calls == ["lifespan"]
    assert get_trace_id() is None


@pytest.mark.asyncio
async def test_trace_id_middleware_establishes_root_trace_id() -> None:
    captured: list[str | None] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        captured.append(get_root_trace_id())

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        pass

    middleware = TraceIDMiddleware(app)
    await middleware({"type": "http", "headers": []}, receive, send)
    assert captured[0] is not None
    assert get_root_trace_id() is None
