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

"""The generic forktex tool API — one FastAPI app, domains at root paths.

forktex-py owns one HTTP surface for its whole tool space. Each domain mounts
at a root path (``/knowledge``, ``/arch``, ``/fsd`` …); every :class:`Tool` in a
domain becomes one ``POST /{domain}/{op}`` endpoint over the *same* registry the
CLI and the agent loop use — no logic duplication, one source of truth.

``fastapi_mcp`` is mounted on the whole app, so every route across every domain
becomes an MCP tool automatically (MCP-over-HTTP at ``/mcp``). The thin stdio
entry (``forktex knowledge mcp``) reuses the same ``mcp`` lib these pull in — one
optional extra (``forktex-py[mcp]``), not two surfaces to maintain.
"""

from __future__ import annotations

import json
from typing import Any

from forktex.agent.tools.base import Tool

#: JSON-Schema scalar type → Python type, for building per-tool request models.
_JSON_PY: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _op_name(domain: str, tool_name: str) -> str:
    """Strip a redundant ``{domain}_`` prefix so paths read ``/knowledge/search``."""
    prefix = f"{domain}_"
    return tool_name[len(prefix):] if tool_name.startswith(prefix) else tool_name


def _request_model(tool: Tool):
    """Build a Pydantic model from a tool's JSON-Schema params.

    Giving each route a real typed body means FastAPI emits a proper OpenAPI
    schema — which is exactly what ``fastapi_mcp`` reflects into the MCP tool's
    input schema, so agents see the real parameters, not an opaque ``object``.
    """
    from pydantic import Field, create_model

    schema = tool.parameters or {}
    props: dict[str, dict] = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, tuple] = {}
    for key, spec in props.items():
        py = _JSON_PY.get(spec.get("type", "string"), str)
        desc = spec.get("description")
        if key in required:
            fields[key] = (py, Field(..., description=desc))
        else:
            fields[key] = (py | None, Field(spec.get("default", None), description=desc))
    model_name = f"{tool.name.title().replace('_', '')}In"
    return create_model(model_name, **fields) if fields else create_model(model_name)


def _coerce(content: str) -> Any:
    """Tool content is a JSON string for structured tools, plain text otherwise."""
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content


def _register_tool(router, domain: str, tool: Tool) -> None:
    from fastapi import HTTPException

    Model = _request_model(tool)
    op = _op_name(domain, tool.name)

    async def endpoint(body):
        args = {k: v for k, v in body.model_dump().items() if v is not None}
        result = await tool.execute(**args)
        if result.is_error:
            raise HTTPException(status_code=422, detail=result.content)
        return {"ok": True, "result": _coerce(result.content), "data": result.data}

    # `from __future__ import annotations` stringifies inline hints, so FastAPI
    # can't resolve the closure-local model — bind the real class explicitly.
    endpoint.__annotations__ = {"body": Model, "return": dict}
    endpoint.__doc__ = tool.description
    router.add_api_route(
        f"/{op}",
        endpoint,
        methods=["POST"],
        name=tool.name,
        operation_id=tool.name,  # → the MCP tool name fastapi_mcp derives
        summary=tool.description.split(".")[0] if tool.description else op,
        tags=[domain],
    )


def create_app(
    domains: dict[str, list[Tool]],
    *,
    title: str = "forktex tool API",
    mount_mcp: bool = True,
    extra_routers: list[tuple[str, Any]] | None = None,
    mcp_exclude_tags: list[str] | None = None,
):
    """Build the generic forktex tool API from a ``{domain: [Tool, …]}`` map.

    Every tool becomes ``POST /{domain}/{op}``; ``fastapi_mcp`` (when available)
    mounts the whole app at ``/mcp`` so each route is also an MCP tool.

    ``extra_routers`` is a list of ``(prefix, APIRouter)`` for non-tool surfaces
    (e.g. the human graph viewer under ``/arch``); ``mcp_exclude_tags`` keeps
    those out of the MCP tool set (the agent uses the structured tool routes).
    """
    from fastapi import APIRouter, FastAPI

    app = FastAPI(
        title=title,
        version="0.8.0",
        summary="One tool surface for forktex — knowledge · arch · fsd — over HTTP + MCP.",
    )

    @app.get("/health", tags=["meta"], operation_id="health")
    async def health() -> dict:
        return {
            "ok": True,
            "domains": {d: [t.name for t in tools] for d, tools in domains.items()},
        }

    for domain, tools in domains.items():
        router = APIRouter(prefix=f"/{domain}")
        for tool in tools:
            _register_tool(router, domain, tool)
        app.include_router(router)
    app.state.domains = list(domains)

    for prefix, router in extra_routers or []:
        app.include_router(router, prefix=prefix)

    if mount_mcp:
        try:
            from fastapi_mcp import FastApiMCP

            FastApiMCP(
                app,
                name=title,
                exclude_tags=(["meta", *(mcp_exclude_tags or [])]) or None,
            ).mount()
        except ImportError:
            # MCP is the optional [mcp] extra; the HTTP API still works without it.
            pass

    return app


__all__ = ["create_app"]
