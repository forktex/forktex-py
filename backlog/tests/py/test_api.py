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

"""Battle tests for the generic forktex tool API (``forktex.api``).

Skips when the optional ``[mcp]`` extra (FastAPI) isn't installed — the API is
an opt-in adapter over the same tools the CLI/agent use.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from starlette.testclient import TestClient  # noqa: E402

from forktex.api.app import create_app  # noqa: E402
from forktex.agent.tools.base import Tool, ToolResult  # noqa: E402


async def _echo(**kw):
    import json

    return ToolResult(content=json.dumps({"echoed": kw}))


def _stub_domains():
    tool = Tool(
        name="demo_ping",
        description="Ping. Returns its arguments.",
        parameters={
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
            "additionalProperties": False,
        },
        handler=_echo,
    )
    return {"demo": [tool]}


def test_create_app_mounts_tools_and_health():
    app = create_app(_stub_domains(), mount_mcp=False)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert "demo" in health.json()["domains"]


def test_tool_route_strips_domain_prefix_and_executes():
    app = create_app(_stub_domains(), mount_mcp=False)
    client = TestClient(app)

    # demo_ping → POST /demo/ping (the `demo_` prefix is stripped)
    resp = client.post("/demo/ping", json={"msg": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["result"] == {"echoed": {"msg": "hi"}}


def test_tool_route_has_typed_openapi_schema():
    app = create_app(_stub_domains(), mount_mcp=False)
    client = TestClient(app)

    spec = client.get("/openapi.json").json()
    op = spec["paths"]["/demo/ping"]["post"]
    # operation_id is the tool name → the MCP tool name fastapi_mcp derives
    assert op["operationId"] == "demo_ping"
    ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    model = spec["components"]["schemas"][ref.split("/")[-1]]
    assert "msg" in model["properties"]  # real typed param, not opaque object


def test_error_result_maps_to_422():
    async def _boom(**kw):
        return ToolResult(content="nope", is_error=True)

    tool = Tool(
        name="demo_boom",
        description="Always errors.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_boom,
    )
    app = create_app({"demo": [tool]}, mount_mcp=False)
    client = TestClient(app)
    resp = client.post("/demo/boom", json={})
    assert resp.status_code == 422


def test_build_domains_assembles_real_tool_set(tmp_path):
    from forktex.api.registry import build_domains

    domains = build_domains(tmp_path, read_only=True)
    assert set(domains) >= {"knowledge", "arch", "fsd"}
    knowledge_names = {t.name for t in domains["knowledge"]}
    assert "knowledge_search" in knowledge_names
    # read-only → no write tools exposed
    assert "knowledge_recycle" not in knowledge_names
