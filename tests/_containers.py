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

from typing import Any
from urllib.parse import urlparse

from sqlalchemy.engine import URL


def start_postgres() -> tuple[Any, URL]:
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:17-alpine")
    container.start()
    raw = container.get_connection_url()
    parsed = urlparse(raw)
    url = URL.create(
        drivername="postgresql+asyncpg",
        username=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path.lstrip("/"),
        query={"ssl": "disable"},
    )
    return container, url


def start_redis() -> tuple[Any, str]:
    from testcontainers.redis import RedisContainer

    container = RedisContainer("redis:7-alpine")
    container.start()
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)
    return container, f"redis://{host}:{port}/0"


def start_minio(bucket: str = "test-bucket") -> tuple[Any, dict[str, str]]:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    container = (
        DockerContainer(
            "pgsty/silo:RELEASE.2026-10-18T00-00-00Z@sha256:2636fc4155d9a7e41ff58cdb65ddd13ba9304e67184e13c25bc5cb34016269d7"
        )
        .with_command("server /data --console-address :9001")
        .with_env("MINIO_ROOT_USER", "minioadmin")
        .with_env("MINIO_ROOT_PASSWORD", "minioadmin")
        .with_exposed_ports(9000, 9001)
    )
    container.start()
    wait_for_logs(container, "API", timeout=30)

    host = container.get_container_host_ip()
    port = container.get_exposed_port(9000)
    url = f"http://{host}:{port}"
    config = {
        "url": url,
        "bucket": bucket,
        "access_key": "minioadmin",
        "secret_key": "minioadmin",
    }
    return container, config


async def ensure_minio_bucket(config: dict[str, str]) -> None:
    try:
        import aioboto3
    except ImportError:
        return

    session = aioboto3.Session(
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
    )
    async with session.client("s3", endpoint_url=config["url"]) as s3:
        try:
            await s3.create_bucket(Bucket=config["bucket"])
        except Exception:
            pass


def start_qdrant() -> tuple[Any, str]:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    container = DockerContainer("qdrant/qdrant:v1.18.1").with_exposed_ports(6333, 6334)
    container.start()
    wait_for_logs(container, "Qdrant gRPC", timeout=30)
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6333)
    return container, f"http://{host}:{port}"


def start_mongo() -> tuple[Any, str]:
    import time

    from pymongo import MongoClient
    from testcontainers.mongodb import MongoDbContainer

    container = MongoDbContainer("mongo:7", username=None, password=None).with_command(
        "mongod --replSet rs0 --bind_ip_all"
    )
    container.username = ""
    container.password = ""
    container.start()

    host = container.get_container_host_ip()
    port = container.get_exposed_port(27017)
    url = f"mongodb://{host}:{port}/?directConnection=true"

    admin = MongoClient(url, serverSelectionTimeoutMS=10_000)
    try:
        admin.admin.command("ping")
        admin.admin.command(
            "replSetInitiate",
            {"_id": "rs0", "members": [{"_id": 0, "host": "localhost:27017"}]},
        )
        for _ in range(30):
            time.sleep(1)
            try:
                if admin.admin.command("replSetGetStatus").get("myState") == 1:
                    break
            except Exception:
                continue
        else:
            raise RuntimeError("MongoDB replica set did not reach PRIMARY state in time")
    finally:
        admin.close()

    return container, url
