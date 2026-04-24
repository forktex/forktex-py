"""Collect live auth state across all three facets, with optional reachability probes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from forktex.agent.auth.store import load_state
from forktex.agent.auth.types import FACETS, AuthState, Facet

_PROBE_TIMEOUT_S = 2.0


async def collect_auth_status(
    project_root: Optional[Path] = None,
    *,
    probe: bool = True,
) -> dict[Facet, AuthState]:
    """Return an AuthState per facet. If *probe* is True, also ping each
    configured facet with a short timeout and fill in ``reachable``.
    """
    states: dict[Facet, AuthState] = {
        facet: load_state(facet, project_root) for facet in FACETS
    }
    if not probe:
        return states

    tasks = []
    for facet, state in states.items():
        if state.configured:
            tasks.append(_probe(facet, state))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    return states


async def _probe(facet: Facet, state: AuthState) -> None:
    try:
        if facet == "cloud":
            await _probe_cloud(state)
        elif facet == "intelligence":
            await _probe_intelligence(state)
        else:
            await _probe_network(state)
    except Exception as exc:  # best-effort; any failure = unreachable
        state.reachable = False
        state.error = _short_err(exc)


async def _probe_cloud(state: AuthState) -> None:
    import httpx

    assert state.endpoint
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
        resp = await client.get(f"{state.endpoint.rstrip('/')}/api/health")
    state.reachable = resp.status_code < 500
    if resp.is_success:
        try:
            body = resp.json()
            if isinstance(body, dict) and "status" in body:
                state.detail["health"] = str(body["status"])
        except Exception:
            pass


async def _probe_intelligence(state: AuthState) -> None:
    from forktex_intelligence.client.client import ForktexIntelligenceClient
    from forktex.agent.intelligence.settings import load_intelligence_settings

    settings = load_intelligence_settings()
    client = ForktexIntelligenceClient(settings.endpoint, settings.api_key)
    try:
        health = await asyncio.wait_for(client.health(), timeout=_PROBE_TIMEOUT_S)
        state.reachable = True
        if getattr(health, "version", None):
            state.detail["version"] = str(health.version)
        try:
            whoami = await asyncio.wait_for(client.whoami(), timeout=_PROBE_TIMEOUT_S)
            if isinstance(whoami, dict):
                if whoami.get("org_id"):
                    state.principal = str(whoami["org_id"])
                    state.detail["org_id"] = state.principal
                if whoami.get("model"):
                    state.detail["model"] = str(whoami["model"])
        except Exception:
            pass
    finally:
        await client.close()


async def _probe_network(state: AuthState) -> None:
    from forktex.agent.network.client_factory import build_network_client
    from forktex.agent.network.settings import load_network_settings

    settings = load_network_settings()
    client = build_network_client(settings)
    try:
        me = await asyncio.wait_for(client.identity_me(), timeout=_PROBE_TIMEOUT_S)
        state.reachable = True
        if getattr(me, "email", None):
            state.principal = str(me.email)
    finally:
        await client.close()


def _short_err(exc: BaseException) -> str:
    msg = str(exc)
    if not msg:
        msg = exc.__class__.__name__
    return msg if len(msg) <= 80 else msg[:77] + "..."
