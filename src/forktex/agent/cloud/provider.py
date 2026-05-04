# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial

"""forktex cloud provider — manage compute and DNS provider credentials."""

from __future__ import annotations

import asyncclick as click


@click.group()
def provider():
    """Manage compute and DNS provider credentials."""


@provider.command("list")
@click.pass_context
async def provider_list(ctx):
    """List all registered provider credentials."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        creds = client.list_providers()
        if not creds:
            click.echo("  No provider credentials registered.")
            return
        for c in creds:
            status = click.style("✓", fg="green") if getattr(c, "isActive", True) else click.style("✗", fg="red")
            last_used = getattr(c, "lastUsedAt", None) or "never"
            click.echo(f"  {status}  {getattr(c, 'id', '?')}  {getattr(c, 'provider', '?'):12}  {getattr(c, 'kind', '?'):8}  {getattr(c, 'label', '')}  last_used={last_used}")


@provider.command("add")
@click.argument("kind", type=click.Choice(["compute", "dns"]))
@click.option("--token", required=True, help="API token or credential string")
@click.option("--label", default="", help="Optional label to identify this credential")
@click.option("--env", default=None, help="Scope to a specific environment name")
@click.pass_context
async def provider_add(ctx, kind, token, label, env):
    """Register a provider credential.

    KIND is 'compute' (for VPS provisioning) or 'dns' (for DNS management).
    The provider vendor (Hetzner, Cloudflare, etc.) is detected automatically.

    \b
    Examples:
        forktex cloud provider add compute --token <hetzner-token>
        forktex cloud provider add dns --token <cloudflare-token>
    """
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    provider_name = _detect_provider(kind, token)

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        cred = client.add_provider(
            provider=provider_name,
            kind=kind,
            payload={"token": token},
            label=label or f"{provider_name}-{kind}",
            environment=env,
        )
        click.echo(f"  ✓  {kind} credential registered")
        click.echo(f"     id={getattr(cred, 'id', '?')}  provider={getattr(cred, 'provider', '?')}")

        # Auto-verify after adding
        cred_id = str(getattr(cred, "id", ""))
        if cred_id:
            result = client.verify_provider(cred_id)
            ok = result.get("ok", result.get("verified", False)) if isinstance(result, dict) else getattr(result, "ok", False)
            if ok:
                click.echo(f"     {click.style('verified ✓', fg='green')}")
            else:
                detail = result.get("detail", "") if isinstance(result, dict) else ""
                click.echo(f"     {click.style('verification failed', fg='yellow')}: {detail}")


@provider.command("verify")
@click.argument("credential_id")
@click.pass_context
async def provider_verify(ctx, credential_id):
    """Test connectivity for a provider credential."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        result = client.verify_provider(credential_id)
        ok = result.get("ok", False) if isinstance(result, dict) else getattr(result, "ok", False)
        detail = result.get("detail", "") if isinstance(result, dict) else ""
        if ok:
            click.echo(f"  {click.style('✓ verified', fg='green')}  {detail}")
        else:
            click.echo(f"  {click.style('✗ failed', fg='red')}  {detail}")


@provider.command("remove")
@click.argument("credential_id")
@click.pass_context
async def provider_remove(ctx, credential_id):
    """Remove a provider credential."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        client.delete_provider(credential_id)
        click.echo(f"  ✓  credential {credential_id[:8]}… removed")


def _detect_provider(kind: str, token: str) -> str:
    """Detect the vendor from token format. Returns provider name string."""
    if kind == "compute":
        # Hetzner tokens are 64-char hex strings
        if len(token) == 64 and all(c in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-" for c in token):
            return "hetzner"
        return "hetzner"  # default compute provider
    elif kind == "dns":
        # Cloudflare tokens start with common prefixes or have specific formats
        if token.startswith("cfut_") or token.startswith("cf_"):
            return "cloudflare"
        return "cloudflare"  # default DNS provider
    return "generic"
