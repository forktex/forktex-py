"""Construct a ``NetworkClient`` with credentials resolved from settings."""

from __future__ import annotations

from forktex_network import NetworkClient

from forktex.agent.network.settings import NetworkSettings


def build_network_client(settings: NetworkSettings) -> NetworkClient:
    """Return a ready-to-use async ``NetworkClient``.

    Callers own the lifecycle — remember to ``await client.close()`` or use
    the client as an async context manager.
    """
    if not settings.is_configured:
        raise RuntimeError(
            "network settings are not configured; run `forktex network login` first."
        )
    assert settings.endpoint and settings.jwt_token  # for type-checkers
    return NetworkClient(base_url=settings.endpoint, jwt_token=settings.jwt_token)
