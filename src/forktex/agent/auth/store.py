"""Credential read / write / clear — dispatches to each facet's settings module.

Kept thin on purpose: schemas live in the facet modules, this layer just
normalises the surface the ``auth`` CLI talks to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from forktex_cloud import paths as _cloud_paths

from forktex.agent.auth.types import AuthState, Facet


def _source_for(facet: Facet, scope: str, project_root: Optional[Path]) -> Path:
    if scope == "global":
        if facet == "cloud":
            return _cloud_paths.global_cloud_file()
        if facet == "intelligence":
            return _cloud_paths.global_intelligence_file()
        return _cloud_paths.global_network_file()
    assert project_root is not None, "project scope requires project_root"
    if facet == "cloud":
        # project cloud state is `.forktex/cloud.json` (flat), not the nested
        # cloud/config.json that `project_cloud_file` points at — settings
        # module composes the flat path inline; mirror that here.
        return _cloud_paths.project_dir(project_root) / "cloud.json"
    if facet == "intelligence":
        return _cloud_paths.project_intelligence_file(project_root)
    return _cloud_paths.project_network_file(project_root)


def load_state(facet: Facet, project_root: Optional[Path]) -> AuthState:
    """Return the observed on-disk state for *facet* without network probing."""
    if facet == "cloud":
        return _load_cloud(project_root)
    if facet == "intelligence":
        return _load_intelligence(project_root)
    return _load_network(project_root)


def clear(facet: Facet, scope: str, project_root: Optional[Path]) -> Path:
    """Delete the credential file for *facet* at *scope*. Returns the path
    that was removed (or would have been — call is idempotent)."""
    path = _source_for(facet, scope, project_root)
    if path.exists():
        path.unlink()
    return path


# ── per-facet loaders ─────────────────────────────────────────────────────────


def _load_cloud(project_root: Optional[Path]) -> AuthState:
    from forktex.agent.cloud.settings import load_cloud_context

    ctx = load_cloud_context(project_root)
    configured = bool(ctx.controller and (ctx.account_key or ctx.access_token))
    if not configured:
        return AuthState(facet="cloud", configured=False)
    # Resolve the scope by checking which file actually has the key material.
    scope, source = _resolve_scope("cloud", project_root)
    auth_kind = "api_key" if ctx.account_key else "jwt"
    detail = {}
    if ctx.org_id:
        detail["org_id"] = ctx.org_id
    if ctx.region:
        detail["region"] = ctx.region
    return AuthState(
        facet="cloud",
        configured=True,
        endpoint=ctx.controller,
        principal=ctx.org_id,
        auth_kind=auth_kind,
        scope=scope,
        source_path=source,
        detail=detail,
    )


def _load_intelligence(project_root: Optional[Path]) -> AuthState:
    from forktex.agent.intelligence.settings import load_intelligence_settings

    root_str = str(project_root) if project_root else None
    settings = load_intelligence_settings(project_root=root_str)
    configured = bool(settings.endpoint and settings.api_key)
    if not configured:
        return AuthState(facet="intelligence", configured=False)
    scope, source = _resolve_scope("intelligence", project_root)
    return AuthState(
        facet="intelligence",
        configured=True,
        endpoint=settings.endpoint,
        principal=None,
        auth_kind="api_key",
        scope=scope,
        source_path=source,
    )


def _load_network(project_root: Optional[Path]) -> AuthState:
    from forktex.agent.network.settings import load_network_settings

    settings = load_network_settings(project_root=project_root)
    configured = bool(settings.endpoint and settings.jwt_token)
    if not configured:
        return AuthState(facet="network", configured=False)
    scope, source = _resolve_scope("network", project_root)
    detail = {}
    if settings.authenticated_at:
        detail["since"] = settings.authenticated_at
    return AuthState(
        facet="network",
        configured=True,
        endpoint=settings.endpoint,
        principal=settings.principal_email,
        auth_kind="jwt",
        scope=scope,
        source_path=source,
        detail=detail,
    )


def _resolve_scope(facet: Facet, project_root: Optional[Path]) -> tuple[str, Path]:
    """Report which file the live settings actually resolved to.

    Project overrides global, so we check project first when a project is given.
    """
    if project_root is not None:
        p = _source_for(facet, "project", project_root)
        if p.exists():
            return "project", p
    g = _source_for(facet, "global", None)
    return "global", g
