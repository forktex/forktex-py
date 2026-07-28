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

"""End-to-end tests for the grid studio HTTP interface (the [api] extra).

Skips cleanly when the grid stack isn't installed (`forktex_core[grid]`) or no
Postgres is available (set ``DATABASE_URL`` or install the ``pgserver`` wheel).
Drives the real app over httpx's ASGI transport against a real Postgres.
"""

from __future__ import annotations

import os

import httpx
import pytest
import pytest_asyncio

pytest.importorskip("forktex_core.grid")
pytest.importorskip("asgi_lifespan")
if not os.environ.get("DATABASE_URL"):
    pytest.importorskip("pgserver")

from asgi_lifespan import LifespanManager  # noqa: E402

from forktex.grid.app import build_app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    app = build_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            yield c


async def _make_people(client: httpx.AsyncClient) -> None:
    assert (
        await client.post("/grid/tables", json={"slug": "people", "label": "People"})
    ).status_code == 201
    for col in (
        {"key": "name", "label": "Name", "type_id": "text", "is_required": True},
        {"key": "age", "label": "Age", "type_id": "integer"},
    ):
        assert (
            await client.post("/grid/tables/people/columns", json=col)
        ).status_code == 201


async def test_types_describe_capabilities(client: httpx.AsyncClient) -> None:
    types = (await client.get("/grid/types")).json()
    by_id = {t["type_id"]: t for t in types}
    assert {"text", "integer", "ref", "enum"} <= set(by_id)
    assert by_id["text"]["capabilities"]["fuzzy"] is True
    assert by_id["integer"]["capabilities"]["sortable"] is True
    assert by_id["json"]["capabilities"]["filterable"] is False


async def test_dynamic_config_and_describe(client: httpx.AsyncClient) -> None:
    await _make_people(client)
    desc = (await client.get("/grid/tables/people")).json()
    assert [c["key"] for c in desc["columns"]] == ["name", "age"]
    age = next(c for c in desc["columns"] if c["key"] == "age")
    assert age["capabilities"]["sortable"] is True


async def test_row_write_normalizes_and_query_filters(
    client: httpx.AsyncClient,
) -> None:
    await _make_people(client)
    created = (
        await client.post(
            "/grid/tables/people/rows", json={"values": {"name": "Alice", "age": "30"}}
        )
    ).json()
    assert created["payload"] == {
        "name": "Alice",
        "age": 30,
    }  # "30" normalized to int by the type handler
    await client.post(
        "/grid/tables/people/rows", json={"values": {"name": "Bob", "age": 12}}
    )

    result = (
        await client.post(
            "/grid/tables/people/query",
            json={
                "filter": {"column": "age", "op": "gte", "value": 18},
                "sort": [{"column": "age"}],
            },
        )
    ).json()
    assert [r["payload"]["name"] for r in result["rows"]] == ["Alice"]


async def test_required_field_rejected(client: httpx.AsyncClient) -> None:
    await _make_people(client)
    r = await client.post("/grid/tables/people/rows", json={"values": {"age": 5}})
    assert r.status_code == 400


async def test_ref_column_without_relation_rejected(client: httpx.AsyncClient) -> None:
    await _make_people(client)
    r = await client.post(
        "/grid/tables/people/columns",
        json={"key": "owner", "label": "Owner", "type_id": "ref"},
    )
    assert r.status_code == 400


async def test_relation_and_links(client: httpx.AsyncClient) -> None:
    for slug in ("orders", "customers"):
        await client.post("/grid/tables", json={"slug": slug, "label": slug.title()})
    await client.post(
        "/grid/tables/orders/relations",
        json={
            "key": "customer",
            "target_slug": "customers",
            "relation_type": "one_to_many",
        },
    )
    order = (await client.post("/grid/tables/orders/rows", json={"values": {}})).json()
    customer = (
        await client.post("/grid/tables/customers/rows", json={"values": {}})
    ).json()
    relate = await client.post(
        f"/grid/tables/orders/rows/{order['id']}/relate",
        json={"relation_key": "customer", "target_row_id": customer["id"]},
    )
    assert relate.status_code == 204
    links = (
        await client.get(
            f"/grid/tables/orders/rows/{order['id']}/links",
            params={"relation_key": "customer"},
        )
    ).json()
    assert [r["id"] for r in links] == [customer["id"]]
