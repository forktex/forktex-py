"""Integration tests for ForktexCloudClient against a real Cloud API.

Uses testcontainers for Postgres and uvicorn in a background thread so the
sync httpx.Client in ForktexCloudClient talks real HTTP.

Requires: uvicorn, testcontainers, sqlalchemy (not in default dev deps).
"""

from __future__ import annotations

import os
import sys
import socket
import threading
import time
import uuid

import pytest

# Skip entire module if integration test deps are missing
uvicorn = pytest.importorskip("uvicorn", reason="uvicorn required for cloud integration tests")
pytest.importorskip("testcontainers", reason="testcontainers required for cloud integration tests")
pytest.importorskip("sqlalchemy", reason="sqlalchemy required for cloud integration tests")

from urllib.parse import urlparse

# Ensure the Cloud API package is importable
CLOUD_API_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "forktex", "cloud", "api")
CLOUD_API_DIR = os.path.normpath(CLOUD_API_DIR)
if CLOUD_API_DIR not in sys.path:
    sys.path.insert(0, CLOUD_API_DIR)

# Must set TEST_ENV before importing app modules
os.environ["TEST_ENV"] = "true"

from testcontainers.postgres import PostgresContainer  # noqa: E402
from sqlalchemy.engine.url import URL  # noqa: E402

from forktex_cloud.client.client import ForktexCloudClient, CloudAPIError  # noqa: E402
from forktex_cloud.client.models import (  # noqa: E402
    ApiKeyCreated,
    ApiKeyRead,
    HealthRead,
    MeResponse,
    OrgRead,
    ProjectRead,
    ServerRead,
    TokenResponse,
    UserRead,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def postgres_url():
    """Start a Postgres testcontainer and return an asyncpg URL string."""
    container = PostgresContainer("postgres:15-alpine")
    container.start()
    url = container.get_connection_url()
    parsed = urlparse(url)
    async_url = URL.create(
        drivername="postgresql+asyncpg",
        username=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path.lstrip("/"),
        query={"ssl": "disable"},
    )
    yield async_url.render_as_string(hide_password=False)
    container.stop()


@pytest.fixture(scope="session")
def cloud_server(postgres_url):
    """Start a uvicorn server running the Cloud API in a background thread."""
    from app.database import connection as db_connection
    from app.database.models import BaseDBModel
    from app.environment import settings
    import asyncio

    settings.db_url = postgres_url

    # Initialize DB and create tables
    async def _init_db():
        db_connection.init_engine(postgres_url, echo=False)
        async with db_connection.engine.begin() as conn:
            await conn.run_sync(BaseDBModel.metadata.create_all)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_init_db())

    from app.main import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.2)
    else:
        raise TimeoutError("Cloud API server did not start in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def unauthed_client(cloud_server) -> ForktexCloudClient:
    """Client without any auth — for health and registration."""
    return ForktexCloudClient(cloud_server)


@pytest.fixture
def user_credentials():
    """Generate unique user credentials."""
    return {
        "email": f"test-{uuid.uuid4().hex[:8]}@example.com",
        "password": "testpass123",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthNoAuth:
    def test_health_returns_ok(self, unauthed_client):
        result = unauthed_client.health()
        assert isinstance(result, HealthRead)
        assert result.status == "ok"


class TestRegisterAndLogin:
    def test_register_returns_user(self, unauthed_client, user_credentials):
        result = unauthed_client.register(
            user_credentials["email"], user_credentials["password"]
        )
        assert isinstance(result, UserRead)
        assert result.id is not None
        assert result.email == user_credentials["email"]

    def test_login_returns_token(self, unauthed_client, user_credentials):
        # Register first
        unauthed_client.register(
            user_credentials["email"], user_credentials["password"]
        )
        result = unauthed_client.login(
            user_credentials["email"], user_credentials["password"]
        )
        assert isinstance(result, TokenResponse)
        assert result.access_token
        assert result.token_type == "bearer"

    def test_login_wrong_password_fails(self, unauthed_client, user_credentials):
        unauthed_client.register(
            user_credentials["email"], user_credentials["password"]
        )
        with pytest.raises(CloudAPIError) as exc_info:
            unauthed_client.login(user_credentials["email"], "wrongpass")
        assert exc_info.value.status_code == 401

    def test_duplicate_register_fails(self, unauthed_client, user_credentials):
        unauthed_client.register(
            user_credentials["email"], user_credentials["password"]
        )
        with pytest.raises(CloudAPIError) as exc_info:
            unauthed_client.register(
                user_credentials["email"], user_credentials["password"]
            )
        assert exc_info.value.status_code == 409


class TestOrgsAfterRegister:
    def test_default_org_exists(self, cloud_server, user_credentials):
        client = ForktexCloudClient(cloud_server)
        client.register(user_credentials["email"], user_credentials["password"])
        token_resp = client.login(
            user_credentials["email"], user_credentials["password"]
        )
        authed = ForktexCloudClient(
            cloud_server, access_token=token_resp.access_token
        )
        orgs = authed.list_orgs()
        assert len(orgs) >= 1
        assert isinstance(orgs[0], OrgRead)
        assert orgs[0].id is not None
        assert orgs[0].name is not None


class TestOrgScopedCRUD:
    """Test project and server CRUD through org-scoped routes."""

    @pytest.fixture
    def authed_client(self, cloud_server, user_credentials):
        """Register, login, and return an org-scoped client."""
        client = ForktexCloudClient(cloud_server)
        client.register(user_credentials["email"], user_credentials["password"])
        token_resp = client.login(
            user_credentials["email"], user_credentials["password"]
        )
        token = token_resp.access_token
        authed = ForktexCloudClient(cloud_server, access_token=token)
        orgs = authed.list_orgs()
        org_id = str(orgs[0].id)
        return ForktexCloudClient(
            cloud_server, access_token=token, org_id=org_id
        )

    def test_create_and_list_projects(self, authed_client):
        result = authed_client.create_project(f"proj-{uuid.uuid4().hex[:8]}")
        assert isinstance(result, ProjectRead)
        assert result.id is not None

        projects = authed_client.list_projects()
        assert len(projects) >= 1
        assert any(p.id == result.id for p in projects)

    def test_get_project(self, authed_client):
        created = authed_client.create_project(f"proj-{uuid.uuid4().hex[:8]}")
        fetched = authed_client.get_project(str(created.id))
        assert fetched.id == created.id

    def test_create_and_list_servers(self, authed_client):
        # Create a project first (servers need one)
        proj = authed_client.create_project(f"proj-{uuid.uuid4().hex[:8]}")
        result = authed_client.create_server(
            f"srv-{uuid.uuid4().hex[:8]}", project_id=str(proj.id)
        )
        assert isinstance(result, ServerRead)
        assert result.id is not None

        servers = authed_client.list_servers()
        assert len(servers) >= 1


class TestApiKeyAuth:
    """Test that org-scoped API keys work as an auth method."""

    def test_api_key_crud_and_auth(self, cloud_server, user_credentials):
        # Register and login
        client = ForktexCloudClient(cloud_server)
        client.register(user_credentials["email"], user_credentials["password"])
        token_resp = client.login(
            user_credentials["email"], user_credentials["password"]
        )
        token = token_resp.access_token
        authed = ForktexCloudClient(cloud_server, access_token=token)
        orgs = authed.list_orgs()
        org_id = str(orgs[0].id)

        # Create API key
        jwt_client = ForktexCloudClient(
            cloud_server, access_token=token, org_id=org_id
        )
        key_resp = jwt_client.create_api_key("test-key")
        assert isinstance(key_resp, ApiKeyCreated)
        assert key_resp.raw_key
        raw_key = key_resp.raw_key

        # List API keys
        keys = jwt_client.list_api_keys()
        assert len(keys) >= 1
        assert isinstance(keys[0], ApiKeyRead)

        # Use API key for auth
        key_client = ForktexCloudClient(
            cloud_server, account_key=raw_key, org_id=org_id
        )
        projects = key_client.list_projects()
        assert isinstance(projects, list)

        # Delete API key
        key_id = key_resp.id
        jwt_client.delete_api_key(str(key_id))


class TestWrongOrgRejected:
    """Verify that accessing another org's resources is rejected."""

    def test_cannot_access_other_org(self, cloud_server):
        # Create two users
        client = ForktexCloudClient(cloud_server)

        email1 = f"user1-{uuid.uuid4().hex[:8]}@example.com"
        email2 = f"user2-{uuid.uuid4().hex[:8]}@example.com"
        password = "testpass123"

        client.register(email1, password)
        client.register(email2, password)

        # User 1 gets their org
        token1 = client.login(email1, password).access_token
        authed1 = ForktexCloudClient(cloud_server, access_token=token1)
        org1_id = str(authed1.list_orgs()[0].id)

        # User 2 gets their org
        token2 = client.login(email2, password).access_token
        authed2 = ForktexCloudClient(cloud_server, access_token=token2)
        org2_id = str(authed2.list_orgs()[0].id)

        # User 2 tries to access user 1's org
        cross_client = ForktexCloudClient(
            cloud_server, access_token=token2, org_id=org1_id
        )
        with pytest.raises(CloudAPIError) as exc_info:
            cross_client.list_projects()
        assert exc_info.value.status_code == 403


class TestMeEndpoint:
    def test_me_returns_user_and_orgs(self, cloud_server, user_credentials):
        client = ForktexCloudClient(cloud_server)
        client.register(user_credentials["email"], user_credentials["password"])
        token_resp = client.login(
            user_credentials["email"], user_credentials["password"]
        )
        authed = ForktexCloudClient(
            cloud_server, access_token=token_resp.access_token
        )
        result = authed.me()
        assert isinstance(result, MeResponse)
        assert result.user.email == user_credentials["email"]
        assert len(result.orgs) >= 1
